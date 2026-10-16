"""部署预检与固定账号容器共用的有限内存预算。"""
import re


def memory_bytes(value: str, allow_zero: bool = False) -> int:
    """解析有限的 MiB/GiB 配置，不接受 Docker 的无限额语法。

    :param value: 0 或正整数加小写 m/g
    :param allow_zero: 是否允许零预算
    :return: 字节数；格式错误时抛出 ValueError
    """
    if allow_zero and value == "0":
        return 0
    match = re.fullmatch(r"([1-9][0-9]*)([mg])", value)
    if not match:
        raise ValueError("内存预算必须为正整数 m/g；swap 可为 0，不能无限额")
    return int(match[1]) * 1024 ** (3 if match[2] == "g" else 2)


def account_limits(memory: str, swap: str = "0") -> tuple[int, int]:
    """统一 RAM 与额外 swap 的语义，返回 Docker 需要的总额度。

    :param memory: RAM 上限
    :param swap: 额外 swap 上限，默认禁用
    :return: RAM 字节数、RAM 加 swap 的总字节数
    """
    ram = memory_bytes(memory)
    return ram, ram + memory_bytes(swap, allow_zero=True)


def isolated_account_limits(memory: str, swap: str = "0") -> dict[str, tuple[int, int]]:
    """在原账号合计上限内划分三个角色，额外 swap 只交给 CLI。

    :param memory: 已固化的账号合计 RAM。
    :param swap: 已固化的账号额外 swap。
    :return: 各角色的 RAM 与 RAM 加 swap 上限；不足时拒绝。
    """
    ram, total = account_limits(memory, swap)
    network, sender = 256 * 1024 ** 2, 128 * 1024 ** 2
    cli = ram - network - sender
    if cli < 512 * 1024 ** 2:
        raise ValueError("账号内存不足以容纳隔离网络、发送器和 CLI，请先明确调整资源预算")
    return {"network": (network, network), "sender": (sender, sender), "cli": (cli, cli + total - ram)}
