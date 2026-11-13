"""模板与恢复实例共用的封存执行映像身份和只读句柄。"""
import fcntl
import hashlib
import os
from pathlib import Path
import stat

IMAGE_NAME = 'ccrb-native-runtime'
IMAGE_LINK = '/memfd:' + IMAGE_NAME + ' (deleted)'
IMAGE_RESOURCE = 'ccrb-executable:' + IMAGE_NAME
REQUIRED_SEALS = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL


def image_identity(descriptor: int, profile: dict) -> tuple[int, int]:
    """检查控制器保护的映像。@param descriptor 只读持有FD。@param profile 固定画像。@return 设备与inode。"""
    info = os.fstat(descriptor)
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 0 or info.st_size != profile['image_bytes']
            or info.st_uid != 0 or info.st_gid != 0 or stat.S_IMODE(info.st_mode) != 0o555
            or os.readlink(f'/proc/self/fd/{descriptor}') != IMAGE_LINK
            or fcntl.fcntl(descriptor, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDONLY
            or fcntl.fcntl(descriptor, fcntl.F_GET_SEALS) & REQUIRED_SEALS != REQUIRED_SEALS):
        raise ValueError('RESTORE_IMAGE_IDENTITY')
    return info.st_dev, info.st_ino


def pin_image(pid: int, profile: dict) -> int:
    """核验种子执行体并固定元数据。@param pid 受控种子PID。@param profile 固定画像。@return 归调用方关闭的FD。"""
    descriptor = os.open(f'/proc/{pid}/exe', os.O_RDONLY | os.O_CLOEXEC)
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 0 or info.st_size != profile['image_bytes']
                or os.readlink(f'/proc/self/fd/{descriptor}') != IMAGE_LINK
                or fcntl.fcntl(descriptor, fcntl.F_GET_SEALS) & REQUIRED_SEALS != REQUIRED_SEALS):
            raise ValueError('RESTORE_IMAGE_IDENTITY')
        digest = hashlib.sha256()
        offset = 0
        while chunk := os.pread(descriptor, 1024 * 1024, offset):
            digest.update(chunk)
            offset += len(chunk)
        if digest.hexdigest() != profile['image_sha256']:
            raise ValueError('RESTORE_IMAGE_IDENTITY')
        # 先固化读执行权限再改属主，确保转换失败时业务UID仍有普通exec条件。
        # 取得所有权后再次固化，消除原属主操作的过渡窗口。
        os.fchmod(descriptor, 0o555)
        os.fchown(descriptor, 0, 0)
        os.fchmod(descriptor, 0o555)
        image_identity(descriptor, profile)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def reopen_image(descriptor: int, profile: dict) -> int:
    """独立打开同一映像。@param descriptor 模板持有FD。@param profile 固定画像。@return 归实例关闭的FD。"""
    identity = image_identity(descriptor, profile)
    opened = os.open(f'/proc/self/fd/{descriptor}', os.O_RDONLY | os.O_CLOEXEC)
    try:
        if image_identity(opened, profile) != identity:
            raise ValueError('RESTORE_IMAGE_IDENTITY')
        return opened
    except BaseException:
        os.close(opened)
        raise


def verify_restored_image(pid: int, descriptor: int, profile: dict) -> None:
    """核对恢复执行体与映射的背板。@param pid 受控PID。@param descriptor 源FD。@param profile 固定画像。@return 无。"""
    identity = image_identity(descriptor, profile)
    executable = os.open(f'/proc/{pid}/exe', os.O_RDONLY | os.O_CLOEXEC)
    try:
        if image_identity(executable, profile) != identity:
            raise ValueError('RESTORE_IMAGE_IDENTITY')
    finally:
        os.close(executable)
    found = False
    for line in Path(f'/proc/{pid}/maps').read_text().splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) != 6 or fields[5] != IMAGE_LINK:
            continue
        major, minor = (int(value, 16) for value in fields[3].split(':'))
        if ((os.makedev(major, minor), int(fields[4])) != identity
                or ('w' in fields[1] and fields[1].endswith('s'))):
            raise ValueError('RESTORE_IMAGE_MAPPING')
        found = True
    if not found:
        raise ValueError('RESTORE_IMAGE_MAPPING')
