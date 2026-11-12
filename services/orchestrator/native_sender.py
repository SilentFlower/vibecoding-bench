"""固定 293 sender 的部署合同与构建输入；不读取账号凭据。"""
import hashlib
import os
import re
import shutil
import urllib.request
from pathlib import Path

from resource_budget import isolated_account_limits, memory_bytes

VERSION = 'v0.1.0-beta.5'
ASSET = 'ccrb-runtime-linux-x64'
SHA256 = '64c61cae565e9097de18cf61a35f46e7595f633cb14f7d6b8c6609fcd294ce89'
POOL_MIB = 256
WORKER_MIB = 192


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
        raise ValueError('原生方式需要显式 V3_NATIVE_SENDER_MEMORY')
    workers = int(configuration.get('concurrency', 3)) * 2
    ram = 0 if unlimited else memory_bytes(value)
    if workers <= 0 or (not unlimited and ram < (POOL_MIB + workers * WORKER_MIB) * 1024 ** 2):
        raise ValueError('原生 sender 预算不足以覆盖账号加权并发')
    isolated_account_limits(memory, swap, value)
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
