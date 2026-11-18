"""历史受管组件的只读profile容量适配，保留原身份验证器。"""
from __future__ import annotations

from inspect import getsource

from account_runtime import _read_json


def profile_reader_source() -> str:
    """生成仅替换JSON文件承载的固定程序。:return: 当前已验证读取器；原身份算法保持原版本。"""
    return 'import account_runtime as _profile_runtime\nexec(' + repr(getsource(_read_json)) + ',_profile_runtime.__dict__)\n'
