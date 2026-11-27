"""隔离验收的只读套接字归属观察。"""

from pathlib import Path
from subprocess import run
import sys


def _has_socket(pid, inode):
    """读取内核中的同进程描述符。@param pid 所属进程。@param inode 套接字 inode。@return 是否持有。"""
    for descriptor in Path(f"/proc/{pid}/fd").iterdir():
        try:
            if descriptor.readlink() == Path(f"socket:[{inode}]"):
                return True
        except FileNotFoundError:
            continue
    return False


def owns_socket(pid, inode):
    """核对选定进程的实际描述符。@param pid 进程。@param inode 套接字。@return 是否持有。"""
    try:
        return _has_socket(pid, inode)
    except PermissionError:
        # 发行 sender 降权运行。用该 UID 读取内核描述符，无需向容器授予额外能力。
        identity = Path(f"/proc/{pid}").stat()
        probe = """
import os
import sys
base = f"/proc/{sys.argv[1]}/fd"
for name in os.listdir(base):
    try:
        if os.readlink(f"{base}/{name}") == f"socket:[{sys.argv[2]}]":
            sys.exit(0)
    except FileNotFoundError:
        continue
sys.exit(1)
"""
        result = run([sys.executable, "-c", probe, str(pid), inode],
                     user=identity.st_uid, group=identity.st_gid, check=False, capture_output=True)
        assert result.returncode in (0, 1) and not result.stderr
        return result.returncode == 0


def loopback_source_inode(peer, port):
    """查回环连接发起端的 inode。@param peer 对端源端口。@param port 监听端口。@return 内核 inode。"""
    source = f"0100007F:{peer:04X}"
    destination = f"0100007F:{port:04X}"
    (inode,) = [row[9] for line in Path("/proc/net/tcp").read_text().splitlines()[1:]
                if (row := line.split())[1:4] == [source, destination, "01"]]
    return inode
