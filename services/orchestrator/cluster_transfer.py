"""经受保护SSH Docker socket有界传输迁移包，避免SDK取消流读取期限。"""
from __future__ import annotations

import hashlib
import os
import re
import tarfile
import time
from pathlib import Path
from stat import S_ISREG

from httpx import Client, HTTPTransport, Timeout

from cluster_deployment import _ArchiveReader


class NodeArchiveTransfer:
    """在固定节点控制容器的操作私有目录中传输迁移包、源码快照和验收报告。

    :param socket_path: 已验证SSH控制隧道的本地Unix socket。
    :param api_version: 已与该Docker daemon协商的API版本。
    :param container: 按部署和节点身份计算的控制容器名称。
    """

    def __init__(self, socket_path: Path, api_version: str, container: str) -> None:
        """冻结受信传输目标。:param socket_path: 私有socket。:param api_version: Docker版本。:param container: 控制容器。:return: None。"""
        if not re.fullmatch(r'1\.[0-9]{1,3}', api_version) or not re.fullmatch('flower2api-node-[a-f0-9]{24}', container):
            raise ValueError('节点归档传输目标无效')
        self.socket_path = socket_path
        self.url = f'http://docker/v{api_version}/containers/{container}/archive'

    def _client(self) -> Client:
        return Client(transport=HTTPTransport(uds=str(self.socket_path), retries=0), trust_env=False,
            follow_redirects=False, timeout=Timeout(connect=8, read=15, write=15, pool=8))

    def _identity(self, operation_id: str, attempt_id: str, checksum: str, size: int) -> None:
        if (not re.fullmatch('[a-f0-9]{32}', operation_id) or not re.fullmatch('[a-f0-9]{32}', attempt_id)
                or not re.fullmatch('[a-f0-9]{64}', checksum) or type(size) is not int or size < 0):
            raise ValueError('迁移包传输身份或大小无效')

    def download(self, operation_id: str, attempt_id: str, target: Path, checksum: str, size: int) -> dict:
        """从固定导出文件逐块下载并校验整包身份，失败清理本次文件。

        :param operation_id: 持久迁移操作。
        :param attempt_id: 源节点已确认的导出尝试。
        :param target: 中央操作私有目录中的全新文件。
        :param checksum: 源组件返回的已核对包摘要。
        :param size: 源组件返回的精确包大小。
        :return: 已核对传输字节数和摘要。
        """
        self._identity(operation_id, attempt_id, checksum, size)
        path = f'/data/node-migrations/{operation_id}/exports/{attempt_id}.tar'
        return self._download(path, attempt_id + '.tar', target, checksum, size, migration=True)

    def download_snapshot(self, environment_id: str, operation_id: str, snapshot_id: str,
                          target: Path, checksum: str, size: int, *, run: bool = False) -> dict:
        """从原终端固定快照文件下载有界源码包。

        :param environment_id: 原冻结环境。
        :param operation_id: 原终端操作。
        :param snapshot_id: 原只读快照尝试。
        :param run: 是否为原Run专属快照目录。
        :param target: 中央本次私有全新文件。
        :param checksum: 节点已冻结整包摘要。
        :param size: 节点已冻结包大小。
        :return: 已核对字节数和摘要。
        """
        self._identity(operation_id, snapshot_id, checksum, size)
        if not re.fullmatch('[a-f0-9]{32}', environment_id) or size > 160 * 1024 * 1024:
            raise ValueError('工程快照范围或大小无效')
        namespace = 'node-runs' if run else 'node-terminals'
        path = f'/data/{namespace}/{environment_id}/{operation_id}/snapshots/{snapshot_id}.tar'
        return self._download(path, snapshot_id + '.tar', target, checksum, size)

    def download_verification(self, environment_id: str, operation_id: str, attempt_id: str,
                              target: Path, checksum: str, size: int, *, run: bool = False) -> dict:
        """下载原节点完整独立程序报告，复用固定单文件归档校验。

        :param environment_id: 原环境。
        :param operation_id: 原终端执行。
        :param attempt_id: 原验收尝试。
        :param target: 中央私有全新文件。
        :param checksum: 原报告摘要。
        :param size: 原报告大小。
        :param run: 是否为已释放Run的独立程序验收。
        :return: 已核对字节数和摘要。
        """
        self._identity(operation_id, attempt_id, checksum, size)
        if not re.fullmatch('[a-f0-9]{32}', environment_id) or not 1 <= size <= 32 * 1024 * 1024:
            raise ValueError('节点验收报告范围或大小无效')
        namespace = 'node-runs' if run else 'node-terminals'
        path = f'/data/{namespace}/{environment_id}/{operation_id}/verifications/{attempt_id}/report.json'
        return self._download(path, 'report.json', target, checksum, size)

    def _download(self, path: str, name: str, target: Path, checksum: str, size: int, *, migration: bool = False) -> dict:
        parent = target.parent.lstat()
        if target.parent.is_symlink() or parent.st_uid != os.geteuid() or parent.st_mode & 0o077:
            raise ValueError('中央迁移中转目录必须为操作私有目录')
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(descriptor, 'wb') as output, self._client() as client, client.stream('GET', self.url,
                    params={'path': path}, headers={'accept-encoding': 'identity'}) as response:
                response.raise_for_status()
                deadline = None if migration else time.monotonic() + 600

                def bounded():
                    count = 0
                    for chunk in response.iter_raw(chunk_size=64 * 1024):
                        count += len(chunk)
                        if count > size + 1024 * 1024 or (deadline is not None and time.monotonic() > deadline):
                            raise ValueError('节点导出包超出传输大小或时间上限')
                        yield chunk

                source = _ArchiveReader(bounded())
                try:
                    with tarfile.open(fileobj=source, mode='r|') as archive:
                        member = archive.next()
                        if (member is None or member.name != name or not member.isfile()
                                or member.size != size):
                            raise ValueError('节点Docker归档与原导出文件不一致')
                        digest = hashlib.sha256()
                        with archive.extractfile(member) as content:
                            while chunk := content.read(1024 * 1024):
                                digest.update(chunk)
                                output.write(chunk)
                        if archive.next() is not None or digest.hexdigest() != checksum:
                            raise ValueError('节点导出包包含额外文件或摘要不匹配')
                    output.flush()
                    os.fsync(output.fileno())
                finally:
                    source.close()
            return {'sha256': checksum, 'bytes': size}
        except BaseException:
            target.unlink(missing_ok=True)
            raise

    def download_login_document(self, environment_id: str, operation_id: str, filename: str,
            target: Path, checksum: str, size: int) -> dict:
        """从原草稿操作的固定冻结目录读取一个有界授权文件。

        :param environment_id: 原NULL草稿环境。
        :param operation_id: 原登录操作。
        :param filename: 固定授权文件枚举。
        :param target: 中央操作私有目录内的全新文件。
        :param checksum: 原Node索引返回的字节摘要。
        :param size: 原Node索引返回的字节数。
        :return: 已核对的完整字节数和摘要。
        """
        self._identity(environment_id,operation_id,checksum,size)
        if filename not in ('.claude.json','.claude/.credentials.json','.claude/settings.json') or not 2<=size<=1024*1024:
            raise ValueError('草稿授权文件超出固定路径或大小范围')
        path=f'/data/node-draft-logins/{environment_id}/{operation_id}/authorization/{filename}'
        return self._download(path,filename.rsplit('/',1)[-1],target,checksum,size)

    def upload(self, operation_id: str, transfer_id: str, source: Path, checksum: str, size: int) -> dict:
        """向目标已创建的操作私有暂存目录流式写入包，保留后续导入核验。

        :param operation_id: 持久迁移操作。
        :param transfer_id: 目标组件已确认的全新暂存尝试。
        :param source: 中央已核对的普通包文件。
        :param checksum: 冻结包摘要。
        :param size: 冻结包大小。
        :return: 已完成上传的摘要和字节数；目标仍须执行独立导入核验。
        """
        self._identity(operation_id, transfer_id, checksum, size)
        path = f'/data/node-migrations/{operation_id}/imports/{transfer_id}'
        return self._upload(path,'environment.tar',source,checksum,size,migration=True)

    def upload_preparation_profile(self, operation_id: str, account_id: int, source: Path, checksum: str, size: int) -> dict:
        """向原节点准备目录上传一个profile。

        :param operation_id: 原准备操作。
        :param account_id: 固定账号。
        :param source: 已过滤私有文件。
        :param checksum: 实际摘要。
        :param size: 实际大小。
        :return: 上传回执。
        """
        self._identity(operation_id, operation_id, checksum, size)
        if type(account_id) is not int or account_id < 1:
            raise ValueError('节点准备账号无效')
        return self._upload(f'/data/node-preparations/{operation_id}/{account_id}', 'profile-' + checksum + '.json',
            source, checksum, size, migration=True)

    def upload_profile(self, operation_id: str, transfer_id: str, source: Path, checksum: str, size: int) -> dict:
        """向原迁移暂存上传固定摘要profile文件。

        :param operation_id: 原迁移。
        :param transfer_id: 原暂存尝试。
        :param source: 私有已投影文件。
        :param checksum: 精确摘要。
        :param size: 实际字节。
        :return: 上传回执。
        """
        self._identity(operation_id, transfer_id, checksum, size)
        return self._upload(f'/data/node-migrations/{operation_id}/imports/{transfer_id}',
            'profile-' + checksum + '.json', source, checksum, size, migration=True)

    def upload_scenario_input(self, environment_id: str, operation_id: str, snapshot_id: str,
                              source: Path, checksum: str, size: int) -> dict:
        """上传本次场景已接受基线，路径固定到原Run私有暂存目录。

        :param environment_id: 原环境。
        :param operation_id: 原Run操作。
        :param snapshot_id: 原源码包身份。
        :param source: 中央完整私有源码包。
        :param checksum: 原整包摘要。
        :param size: 原整包大小。
        :return: 已上传字节与摘要，节点另行核对原Scope和所有对象。
        """
        self._identity(operation_id,snapshot_id,checksum,size)
        if not re.fullmatch('[a-f0-9]{32}',environment_id) or not 10240<=size<=160*1024*1024:
            raise ValueError('场景基线传输的原环境或大小无效')
        path=f'/data/node-runs/{environment_id}/{operation_id}/scenario-inputs/imports/{snapshot_id}'
        return self._upload(path,'snapshot.tar',source,checksum,size)

    def download_scenario_input(self, environment_id: str, operation_id: str, snapshot_id: str,
                                target: Path, checksum: str, size: int) -> dict:
        """下载本次场景真实输入阶段的完整源码包。

        :param environment_id: 原环境。
        :param operation_id: 原Run操作。
        :param snapshot_id: 节点登记阶段包身份。
        :param target: 中央全新私有包文件。
        :param checksum: 原整包摘要。
        :param size: 原整包大小。
        :return: 已核对字节与摘要。
        """
        self._identity(operation_id,snapshot_id,checksum,size)
        if not re.fullmatch('[a-f0-9]{32}',environment_id) or not 10240<=size<=160*1024*1024:
            raise ValueError('场景输入阶段传输的原环境或大小无效')
        path=f'/data/node-runs/{environment_id}/{operation_id}/scenario-inputs/exports/{snapshot_id}.tar'
        return self._download(path,snapshot_id+'.tar',target,checksum,size)

    def _upload(self, path: str, name: str, source: Path, checksum: str, size: int, *, migration: bool = False) -> dict:
        descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, 'rb') as input_file:
            metadata = os.fstat(input_file.fileno())
            if (not S_ISREG(metadata.st_mode) or metadata.st_size != size or metadata.st_mode & 0o077
                    or metadata.st_uid != os.geteuid() or metadata.st_nlink != 1):
                raise ValueError('中央迁移包的类型、大小或权限无效')
            deadline = None if migration else time.monotonic() + 600

            def chunks():
                member = tarfile.TarInfo(name)
                member.mode, member.size = 0o600, size
                yield member.tobuf()
                digest, count = hashlib.sha256(), 0
                while chunk := input_file.read(1024 * 1024):
                    count += len(chunk)
                    if count > size or (deadline is not None and time.monotonic() > deadline):
                        raise ValueError('中央迁移包发生变化或超出传输时间')
                    digest.update(chunk)
                    yield chunk
                if count != size or digest.hexdigest() != checksum:
                    raise ValueError('中央迁移包传输期间摘要发生变化')
                yield b'\0' * ((512 - size % 512) % 512 + 1024)

            with self._client() as client:
                with client.stream('PUT', self.url, params={'path': path, 'noOverwriteDirNonDir': 'true'},
                        headers={'content-type': 'application/x-tar'}, content=chunks()) as response:
                    response.raise_for_status()
                    if response.status_code != 200:
                        raise ValueError('目标Docker未确认迁移包写入')
        return {'sha256': checksum, 'bytes': size}

    def upload_review_input(self, environment_id: str, operation_id: str, source: Path, checksum: str, size: int) -> dict:
        """仅向原Run的私有暂存目录上传完整冻结评审包。

        :param environment_id: 原环境。
        :param operation_id: 原Run操作。
        :param source: 中央原完整私有包文件。
        :param checksum: 原包字节摘要。
        :param size: 原包大小，上限512KiB。
        :return: 已上传字节及摘要，节点另行核对原回答身份。
        """
        self._identity(operation_id,operation_id,checksum,size)
        if not re.fullmatch('[a-f0-9]{32}',environment_id) or not 1<=size<=512*1024:
            raise ValueError('私有评审包的原环境或大小无效')
        return self._upload(f'/data/node-runs/{environment_id}/{operation_id}/review-inputs','package.json',source,checksum,size)
