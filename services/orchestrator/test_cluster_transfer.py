"""Docker归档HTTP边界的迁移包流式读写和失败收口测试。"""
from __future__ import annotations

import hashlib
import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from httpx import ByteStream, Client, MockTransport, Response

from cluster_transfer import NodeArchiveTransfer


class ArchiveTransferTests(unittest.TestCase):
    """用真实HTTPX请求构建与tar解析核对固定路径和原字节。"""

    def setUp(self) -> None:
        """建立操作私有中转目录及可跨块的合成包。:return: None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.transfer = NodeArchiveTransfer(self.root / 'docker.sock', '1.45', 'flower2api-node-' + 'a' * 24)
        self.operation, self.attempt = 'b' * 32, 'c' * 32
        self.payload = b'x' * (2 * 1024 * 1024 + 7)
        self.checksum = hashlib.sha256(self.payload).hexdigest()
        self.source = self.root / 'source.tar'
        self.source.write_bytes(self.payload)
        self.source.chmod(0o600)

    def archive(self, *, name: str | None = None, extra: bool = False) -> bytes:
        """生成Docker外层单文件tar。:param name: 返回文件名。:param extra: 是否附带额外文件。:return: 外层归档。"""
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode='w') as archive:
            member = tarfile.TarInfo(name or self.attempt + '.tar')
            member.size = len(self.payload)
            archive.addfile(member, io.BytesIO(self.payload))
            if extra:
                archive.addfile(tarfile.TarInfo('unexpected'))
        return output.getvalue()

    def transport(self, handler):
        """仅替换网络承载，保留真实客户端编码。:param handler: HTTP模拟服务。:return: 客户端工厂补丁。"""
        return patch.object(self.transfer, '_client', side_effect=lambda: Client(transport=MockTransport(handler), trust_env=False))

    def test_download_checks_exact_container_file_and_private_output(self) -> None:
        """Docker外层归档只接受该操作文件，中央输出权限与内容匹配。:return: None。"""
        def handler(request):
            self.assertEqual('GET', request.method)
            self.assertEqual(f'/data/node-migrations/{self.operation}/exports/{self.attempt}.tar', request.url.params['path'])
            self.assertEqual('identity', request.headers['accept-encoding'])
            return Response(200, stream=ByteStream(self.archive()))
        target = self.root / 'downloaded.tar'
        with self.transport(handler):
            receipt = self.transfer.download(self.operation, self.attempt, target, self.checksum, len(self.payload))
        self.assertEqual(self.payload, target.read_bytes())
        self.assertEqual({'bytes': len(self.payload), 'sha256': self.checksum}, receipt)
        self.assertEqual(0o600, target.stat().st_mode & 0o777)

    def test_verification_report_uses_exact_attempt_file_and_bounded_private_output(self) -> None:
        """完整报告只读取原环境、执行及尝试的固定JSON文件。:return: None。"""
        environment = 'e' * 32

        def handler(request):
            self.assertEqual(f'/data/node-terminals/{environment}/{self.operation}/verifications/{self.attempt}/report.json',
                request.url.params['path'])
            return Response(200, stream=ByteStream(self.archive(name='report.json')))

        target = self.root / 'verification.json'
        with self.transport(handler):
            self.transfer.download_verification(environment, self.operation, self.attempt, target, self.checksum, len(self.payload))
        self.assertEqual(self.payload, target.read_bytes())
        self.assertEqual(0o600, target.stat().st_mode & 0o777)
        with self.assertRaises(ValueError):
            self.transfer.download_verification(environment, self.operation, self.attempt, target, self.checksum, 33 * 1024 * 1024)

    def test_workspace_download_keeps_environment_execution_and_snapshot_path_fixed(self) -> None:
        """快照下载复用原流式校验，仅允许冻结环境和终端的私有文件。:return: None。"""
        environment = 'e' * 32

        def handler(request):
            self.assertEqual(f'/data/node-terminals/{environment}/{self.operation}/snapshots/{self.attempt}.tar',
                request.url.params['path'])
            return Response(200, stream=ByteStream(self.archive()))

        target = self.root / 'snapshot.tar'
        with self.transport(handler):
            self.transfer.download_snapshot(environment, self.operation, self.attempt, target, self.checksum, len(self.payload))
        self.assertEqual(self.payload, target.read_bytes())
        with self.assertRaises(ValueError):
            self.transfer.download_snapshot('../other', self.operation, self.attempt, target, self.checksum, len(self.payload))

    def test_upload_builds_valid_single_file_tar_and_fixed_private_destination(self) -> None:
        """上传为包含原始包的合法tar，目标限定在已创建的操作暂存目录。:return: None。"""
        def handler(request):
            self.assertEqual('PUT', request.method)
            self.assertEqual(f'/data/node-migrations/{self.operation}/imports/{self.attempt}', request.url.params['path'])
            self.assertEqual('true', request.url.params['noOverwriteDirNonDir'])
            with tarfile.open(fileobj=io.BytesIO(request.read()), mode='r:') as archive:
                members = archive.getmembers()
                self.assertEqual(['environment.tar'], [member.name for member in members])
                self.assertEqual(0o600, members[0].mode)
                self.assertEqual(self.payload, archive.extractfile(members[0]).read())
            return Response(200)
        with self.transport(handler):
            self.transfer.upload(self.operation, self.attempt, self.source, self.checksum, len(self.payload))

    def test_scenario_upload_and_stage_download_use_only_original_run_private_paths(self) -> None:
        """场景双向包固定到原环境和操作，上传文件名与阶段导出范围一致。:return: None。"""
        environment='e'*32
        def handler(request):
            if request.method=='PUT':
                self.assertEqual(f'/data/node-runs/{environment}/{self.operation}/scenario-inputs/imports/{self.attempt}',
                    request.url.params['path'])
                with tarfile.open(fileobj=io.BytesIO(request.read()),mode='r:') as archive:
                    self.assertEqual(['snapshot.tar'],[member.name for member in archive.getmembers()])
                    self.assertEqual(self.payload,archive.extractfile('snapshot.tar').read())
                return Response(200)
            self.assertEqual(f'/data/node-runs/{environment}/{self.operation}/scenario-inputs/exports/{self.attempt}.tar',
                request.url.params['path'])
            return Response(200,stream=ByteStream(self.archive(name=self.attempt+'.tar')))
        target=self.root/'scenario-downloaded.tar'
        with self.transport(handler):
            self.transfer.upload_scenario_input(environment,self.operation,self.attempt,self.source,self.checksum,len(self.payload))
            self.transfer.download_scenario_input(environment,self.operation,self.attempt,target,self.checksum,len(self.payload))
        self.assertEqual(self.payload,target.read_bytes())
        with self.assertRaises(ValueError):
            self.transfer.upload_scenario_input('../other',self.operation,self.attempt,self.source,self.checksum,len(self.payload))

    def test_private_review_upload_preserves_complete_package_and_rejects_over_limit(self) -> None:
        """原完整评审包只进入本次固定私有暂存路径，超限在请求前拒绝。:return: None。"""
        environment='e'*32
        source=self.root/'review-package.json'
        raw=b'{"job_id":7,"answer":"fixed local fixture"}'
        source.write_bytes(raw)
        source.chmod(0o600)
        checksum=hashlib.sha256(raw).hexdigest()
        def handler(request):
            self.assertEqual(f'/data/node-runs/{environment}/{self.operation}/review-inputs',request.url.params['path'])
            with tarfile.open(fileobj=io.BytesIO(request.read()),mode='r:') as archive:
                members=archive.getmembers()
                self.assertEqual(['package.json'],[member.name for member in members])
                self.assertEqual(0o600,members[0].mode)
                self.assertEqual(raw,archive.extractfile(members[0]).read())
            return Response(200)
        with self.transport(handler):
            self.transfer.upload_review_input(environment,self.operation,source,checksum,len(raw))
        with self.assertRaises(ValueError):
            self.transfer.upload_review_input(environment,self.operation,source,checksum,512*1024+1)

    def test_wrong_name_extra_member_and_checksum_remove_partial_download(self) -> None:
        """归档范围和摘要分别核对，失败只清理本次输出。:return: None。"""
        for raw, checksum in ((self.archive(name='foreign.tar'), self.checksum),
                (self.archive(extra=True), self.checksum), (self.archive(), '0' * 64)):
            with self.subTest(checksum=checksum[:4]), self.transport(lambda request: Response(200, stream=ByteStream(raw))):
                with self.assertRaises(ValueError):
                    self.transfer.download(self.operation, self.attempt, self.root / 'failed.tar', checksum, len(self.payload))
            self.assertFalse((self.root / 'failed.tar').exists())

    def test_existing_download_target_and_unsafe_input_are_preserved(self) -> None:
        """现有中转文件与非法操作身份均在请求前拒绝。:return: None。"""
        with self.assertRaises(FileExistsError):
            self.transfer.download(self.operation, self.attempt, self.source, self.checksum, len(self.payload))
        self.assertEqual(self.payload, self.source.read_bytes())
        with self.assertRaisesRegex(ValueError, '身份'):
            self.transfer.download('../other', self.attempt, self.root / 'bad.tar', self.checksum, len(self.payload))
        self.assertFalse((self.root / 'bad.tar').exists())

    def test_upload_refuses_changed_file_and_world_readable_bundle(self) -> None:
        """包大小、实际摘要和私有权限分别核对，避免误传旧包或公开凭据文件。:return: None。"""
        with self.transport(lambda request: Response(200)):
            with self.assertRaisesRegex(ValueError, '大小|权限'):
                self.transfer.upload(self.operation, self.attempt, self.source, self.checksum, 1)
            with self.assertRaisesRegex(ValueError, '摘要'):
                self.transfer.upload(self.operation, self.attempt, self.source, '0' * 64, len(self.payload))
            self.source.chmod(0o644)
            with self.assertRaisesRegex(ValueError, '权限'):
                self.transfer.upload(self.operation, self.attempt, self.source, self.checksum, len(self.payload))
