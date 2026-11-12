"""在受控恢复进程暂停期间重置固定 BoringSSL fork 标志。"""
import hashlib
import os
import re
import select
from dataclasses import dataclass
from pathlib import Path

PROC_ROOT = Path('/proc')
PROFILE = 'bun143-wipeonfork-v1'
SMAPS_LIMIT = 16 * 1024 * 1024


class EntropyError(ValueError):
    """恢复过程只暴露白名单错误码。"""


@dataclass(frozen=True)
class ProcessProof:
    """控制器已登记的物理进程身份。@param pid 物理PID。@param owner 命名空间监督父PID。@param started 启动时刻。@param image_sha256 受信模板映像摘要。"""
    pid: int
    owner: int
    started: str
    image_sha256: str


def read_at(directory: int, name: str, maximum: int = 65536) -> bytes:
    """从已持有目录读取有界元数据。@param directory 目录FD。@param name 内部固定名称。@param maximum 字节上限。@return 完整内容。"""
    if name not in {'status', 'stat', 'smaps'}:
        raise EntropyError('RESTORE_METADATA_FIELD')
    descriptor = os.open(name, os.O_RDONLY | os.O_CLOEXEC, dir_fd=directory)
    try:
        chunks = []
        size = 0
        while True:
            chunk = os.read(descriptor, min(65536, maximum + 1 - size))
            if not chunk:
                return b''.join(chunks)
            chunks.append(chunk)
            size += len(chunk)
            if size > maximum:
                raise EntropyError('RESTORE_METADATA_LIMIT')
    finally:
        os.close(descriptor)


def stopped_threads(directory: int, proof: ProcessProof) -> int:
    """检查完整受限线程组仍暂停。@param directory 持有的进程目录FD。@param proof 权威进程身份。@return 线程数。"""
    status = dict(line.split(':', 1) for line in read_at(directory, 'status').decode().splitlines() if ':' in line)
    started = read_at(directory, 'stat').decode().rsplit(')', 1)[1].split()[19]
    if (int(status['PPid']) != proof.owner or started != proof.started
            or [int(value) for value in status['Uid'].split()] != [1001] * 4
            or int(status['CapEff'], 16) != 0 or int(status['NoNewPrivs']) != 1 or int(status['Seccomp']) != 2):
        raise EntropyError('RESTORE_PROCESS_OWNERSHIP')
    tasks = os.open('task', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC, dir_fd=directory)
    try:
        entries = os.listdir(tasks)
        if not entries or len(entries) > 128 or any(not value.isdigit() for value in entries):
            raise EntropyError('RESTORE_THREAD_STATE')
        for entry in entries:
            thread = os.open(entry, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC, dir_fd=tasks)
            try:
                fields = dict(line.split(':', 1) for line in read_at(thread, 'status').decode().splitlines() if ':' in line)
                if fields['State'].split()[0] != 'T' or int(fields['Tgid']) != proof.pid:
                    raise EntropyError('RESTORE_THREAD_STATE')
            finally:
                os.close(thread)
        return len(entries)
    finally:
        os.close(tasks)


def fork_guard(directory: int) -> int:
    """定位固定配方中唯一的匿名 fork 标志页。@param directory 进程目录FD。@return 页起始地址。"""
    regions = []
    current = []
    for line in read_at(directory, 'smaps', SMAPS_LIMIT).decode().splitlines():
        if re.match(r'^[0-9a-f]+-[0-9a-f]+ ', line) and current:
            regions.append(current)
            current = []
        current.append(line)
    if current:
        regions.append(current)
    guards = [region for region in regions if any(line.startswith('VmFlags:') and 'wf' in line.split()[1:] for line in region)]
    if len(guards) != 1:
        raise EntropyError('RESTORE_ENTROPY_PROFILE')
    header = guards[0][0].split()
    start, end = [int(value, 16) for value in header[0].split('-')]
    if len(header) != 5 or header[1:] != ['rw-p', '00000000', '00:00', '0'] or end - start != 4096:
        raise EntropyError('RESTORE_ENTROPY_PROFILE')
    return start


def reset_fork_guard(proof: ProcessProof) -> dict:
    """为控制器持有的恢复副本重新建立原生 fork 代次。@param proof 由受控恢复登记生成的身份，调用方须保持该实例所有权。@return 安全的复位回执。"""
    if (type(proof.pid) is not int or proof.pid < 2 or type(proof.owner) is not int or proof.owner < 1
            or not isinstance(proof.started, str) or not re.fullmatch(r'[0-9]{1,20}', proof.started)
            or not isinstance(proof.image_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', proof.image_sha256)):
        raise EntropyError('RESTORE_PROCESS_OWNERSHIP')
    pidfd = os.pidfd_open(proof.pid)
    directory = None
    try:
        directory = os.open(PROC_ROOT / str(proof.pid), os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        if select.select([pidfd], [], [], 0)[0]:
            raise EntropyError('RESTORE_PROCESS_EXITED')
        count = stopped_threads(directory, proof)
        executable = os.open('exe', os.O_RDONLY | os.O_CLOEXEC, dir_fd=directory)
        try:
            digest = hashlib.sha256()
            while chunk := os.read(executable, 1024 * 1024):
                digest.update(chunk)
            if digest.hexdigest() != proof.image_sha256:
                raise EntropyError('RESTORE_IMAGE_IDENTITY')
        finally:
            os.close(executable)
        address = fork_guard(directory)
        memory = os.open('mem', os.O_RDWR | os.O_CLOEXEC, dir_fd=directory)
        try:
            page = os.pread(memory, 4096, address)
            if page != b'\x01\x00\x00\x00' + bytes(4092):
                raise EntropyError('RESTORE_ENTROPY_PROFILE')
            # BoringSSL 的标志是 WIPEONFORK 页首的 Atomic<uint32_t>。
            # 所有线程仍暂停时模拟内核 fork 清零；之后各线程沿原生分支从系统熵重新播种。
            if stopped_threads(directory, proof) != count or select.select([pidfd], [], [], 0)[0]:
                raise EntropyError('RESTORE_THREAD_STATE')
            if os.pwrite(memory, bytes(4), address) != 4:
                raise EntropyError('RESTORE_ENTROPY_WRITE')
        finally:
            os.close(memory)
        return {'profile': PROFILE, 'guard_bytes': 4, 'stopped_threads': count}
    finally:
        if directory is not None:
            os.close(directory)
        os.close(pidfd)
