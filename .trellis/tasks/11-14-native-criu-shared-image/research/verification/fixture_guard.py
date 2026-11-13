"""防止固定路径实验夹具在普通宿主机直接运行。"""
import os
from pathlib import Path


def require_disposable_guest() -> None:
    """核对一次性客体标记与root身份。@return 无；缺少显式标记时拒绝。"""
    if os.geteuid() != 0 or Path('/probe/.disposable-criu-guest').read_text().strip() != 'offline-synthetic-only':
        raise RuntimeError('只允许在无外部网卡、合成身份的一次性实验客体运行')
