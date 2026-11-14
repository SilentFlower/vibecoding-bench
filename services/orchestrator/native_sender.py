"""固定 293 sender 的部署合同与构建输入；不读取账号凭据。"""
import hashlib
import os
import re
import shutil
import urllib.request
from pathlib import Path

from resource_budget import isolated_account_limits, memory_bytes

VERSION = 'v0.1.0-beta.6'
ASSET = 'ccrb-runtime-linux-x64'
SHA256 = 'fce50a30d739dbc614e450d4d1913208fa35c6373c4f07a3986657393a99261e'
POOL_MIB = 256
WORKER_MIB = 192
RESTORE_IMAGE_MIB = 108


def criu_enabled() -> bool:
    """读取默认开启的部署恢复选择。@return 缺省/空值开启，精确0关闭；非法配置拒绝。"""
    value = os.environ.get('V3_NATIVE_CRIU', '1') or '1'
    if value not in ('0', '1'):
        raise ValueError('原生 CRIU 开关必须为 0 或 1')
    return value == '1'


def prewarm_account_id(value: str) -> int | None:
    """读取预启动试点账号。

    :param value: 配置中的网关账号 ID；空值表示关闭。
    :return: 已校验的正整数或 None。
    """
    if not value:
        return None
    if not re.fullmatch(r"[1-9][0-9]{0,18}", value) or int(value) > 2**63 - 1:
        raise ValueError("V3_NATIVE_PREWARM_ACCOUNT_ID 必须是有效的网关账号 ID")
    return int(value)


class NativePreparationBlocked(ValueError):
    """携带白名单资源原因，供内部准备状态安全投影。"""

    def __init__(self, reason: str, message: str) -> None:
        """保存受控原因。@param reason 固定故障码。@param message 本地说明。@return None。"""
        super().__init__(message)
        self.reason = reason


def sender_config(configuration: dict, memory: str, swap: str = '0', budget: str | None = None) -> dict | None:
    """以权威后端和显式部署预算生成 sender 配置。

    :param configuration: 网关返回的账号后端和标准并发。
    :param memory: 已冻结的账号 RAM 总预算。
    :param swap: 已冻结的额外 swap。
    :param budget: 原生 sender RAM；省略时读取部署环境。
    :return: 原生池配置；legacy 返回 None，预算不足抛出 ValueError。
    """
    backend = configuration.get('request_backend', 'legacy')
    if backend == 'legacy':
        return None
    if backend != 'native293':
        raise ValueError('未知账号请求后端')
    value = os.environ.get('V3_NATIVE_SENDER_MEMORY', '') if budget is None else budget
    unlimited = memory == 'unlimited'
    if not value and not unlimited:
        raise NativePreparationBlocked('native_sender_budget_missing', '原生方式需要显式 V3_NATIVE_SENDER_MEMORY')
    workers = int(configuration.get('concurrency', 3)) * 2
    ram = 0 if unlimited else memory_bytes(value)
    # 恢复预算另行准入；默认开启不能让原先可用的有限账号失去普通启动能力。
    if workers <= 0 or (not unlimited and ram < (POOL_MIB + workers * WORKER_MIB) * 1024 ** 2):
        raise NativePreparationBlocked('native_sender_budget_insufficient', '原生 sender 预算不足以覆盖账号加权并发')
    try:
        isolated_account_limits(memory, swap, value)
    except ValueError as error:
        raise NativePreparationBlocked('account_memory_insufficient', str(error)) from error
    return {'binary_path': '/usr/local/bin/ccrb-runtime', 'work_root': '/native',
            'memory_mib': ram // 1024 ** 2, 'max_workers': workers}


def stage_asset(destination: Path, source: str | None = None) -> dict:
    """把实际发布附件或显式本地候选冻结到本次镜像构建上下文。

    :param destination: 新构建快照内的文件路径。
    :param source: 本地候选文件；省略时读取 V3_NATIVE_RUNTIME_ASSET 或固定发布附件。
    :return: 已校验的版本、大小及 SHA256 记录。
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = source or os.environ.get('V3_NATIVE_RUNTIME_ASSET')
    if source:
        shutil.copyfile(source, destination)
    else:
        url = f'https://github.com/SilentFlower/cc-runtime-bridge/releases/download/{VERSION}/{ASSET}'
        with urllib.request.urlopen(url, timeout=60) as response, destination.open('xb') as output:
            shutil.copyfileobj(response, output)
    if destination.stat().st_size != 27388048 or hashlib.sha256(destination.read_bytes()).hexdigest() != SHA256:
        destination.unlink()
        raise ValueError('原生运行时附件身份不匹配')
    destination.chmod(0o755)
    return {'version': VERSION, 'asset': ASSET, 'sha256': SHA256, 'bytes': 27388048}
