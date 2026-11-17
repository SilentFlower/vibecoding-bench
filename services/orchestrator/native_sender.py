"""280/293原生sender的部署合同与构建输入。"""
import hashlib
import os
import re
import shutil
from pathlib import Path

from resource_budget import isolated_account_limits, memory_bytes

VERSION = 'v0.1.0-beta.7'
ASSET = 'ccrb-runtime-linux-x64'
SHA256 = '9a5eb46175762bbcc84ad069601c9626b35a9bbf41aa53f08e96d32fdcf3198a'
POOL_MIB = 256
WORKER_MIB = 192
RESTORE_IMAGE_MIB = 108
VERSION_280 = 'builtin-2.1.280'
SHA256_280 = '21e7c3f85c698138c027622e1abc1f20b4f684847cce000d5f3ba9ecd9654229'
BYTES_280 = 27097232
BYTES = 27392144


def installed_versions(labels: dict) -> tuple[str, ...]:
    """读取镜像明确提供的固定源版本。@param labels 已核验镜像标签。@return 支持版本集合。"""
    value = labels.get('vibebench.native-runtime-versions')
    if value in (None, '2.1.293'):
        return ('2.1.293',)
    if value != '2.1.280,2.1.293':
        raise ValueError('账号镜像的原生运行时版本集合无效')
    return ('2.1.280', '2.1.293')


def native_resource_layout(configuration: dict | None) -> dict | None:
    """提取与容器资源布局相关的原生配置。@param configuration 已生效或目标配置。@return 排除各版发行选择后的布局。"""
    if configuration is None:
        return None
    result = {key: value for key, value in configuration.items() if key not in ('release', 'kernel_generation')}
    if result.get('source_version') == '2.1.293':
        result.pop('source_version')
    if 'runtimes' in result:
        runtimes = result['runtimes']
        if not isinstance(runtimes, dict) or set(runtimes) - {'2.1.280', '2.1.293'}:
            raise ValueError('原生运行时安装表无效')
        for version, value in runtimes.items():
            expected = '/usr/local/bin/ccrb-runtime-280' if version == '2.1.280' else '/usr/local/bin/ccrb-runtime'
            if (not isinstance(value, dict) or value.get('binary_path') != expected
                    or set(value) - {'binary_path', 'release', 'kernel_generation'}):
                raise ValueError('原生运行时安装路径或字段无效')
        result['runtimes'] = {version: {key: value for key, value in runtime.items()
            if key not in ('release', 'kernel_generation')} for version, runtime in runtimes.items()}
    return result


def builtin_config(configuration: dict | None, versions: tuple[str, ...]) -> dict | None:
    """按目标镜像归一化内核安装表，保留已经冻结的资源和账号布局。

    :param configuration: 已校验的目标或历史原生配置。
    :param versions: 目标镜像明确声明的官方源版本集合。
    :return: 仅引用镜像内置程序的配置；基础后端保持None。
    """
    if versions not in (('2.1.293',), ('2.1.280', '2.1.293')):
        raise ValueError('原生运行时版本集合无效')
    result = native_resource_layout(configuration)
    if result is None:
        return None
    # 安装表属于目标镜像；沿用旧表会使升级后的首笔API再次要求重建整个环境。
    result['binary_path'] = '/usr/local/bin/ccrb-runtime'
    result.pop('source_version', None)
    result.pop('runtimes', None)
    if '2.1.280' in versions:
        result['runtimes'] = {'2.1.280': {'binary_path': '/usr/local/bin/ccrb-runtime-280'}}
    return result


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


def sender_config(configuration: dict, memory: str, swap: str = '0', budget: str | None = None,
                  versions: tuple[str, ...] = ('2.1.293',)) -> dict | None:
    """以权威后端和显式部署预算生成 sender 配置。

    :param configuration: 网关返回的账号后端和标准并发。
    :param memory: 已冻结的账号 RAM 总预算。
    :param swap: 已冻结的额外 swap。
    :param budget: 原生 sender RAM；省略时读取部署环境。
    :param versions: 已核验镜像提供的源版本集合，历史镜像仅293。
    :return: 原生池配置；legacy 返回 None，配置或账号总预算无效时抛出 ValueError。
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
    if versions not in (('2.1.293',), ('2.1.280', '2.1.293')):
        raise ValueError('原生运行时版本集合无效')
    if workers <= 0:
        raise ValueError('原生 sender 的账号并发必须为正数')
    try:
        isolated_account_limits(memory, swap, value)
    except ValueError as error:
        raise NativePreparationBlocked('account_memory_insufficient', str(error)) from error
    result = {'binary_path': '/usr/local/bin/ccrb-runtime', 'work_root': '/native',
              'memory_mib': ram // 1024 ** 2, 'max_workers': workers}
    if '2.1.280' in versions:
        result['runtimes'] = {'2.1.280': {'binary_path': '/usr/local/bin/ccrb-runtime-280'}}
    return result


def stage_asset(destination: Path, source: str | None = None, version: str = '2.1.293') -> dict:
    """将本仓库已验收制品冻结到本次镜像构建上下文。

    :param destination: 新构建快照内的文件路径。
    :param source: 本仓库准备的本地制品；省略时读取对应构建环境变量。
    :param version: 明确的官方源版本，历史入口为293。
    :return: 已校验的版本、大小及 SHA256 记录。
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    if version not in ('2.1.280', '2.1.293'):
        raise ValueError('未知原生运行时源版本')
    if version == '2.1.280':
        source = source or os.environ.get('V3_NATIVE_RUNTIME_280_ASSET')
        if not source:
            raise ValueError('构建双版本镜像需要 V3_NATIVE_RUNTIME_280_ASSET 指向已验收的280制品')
        shutil.copyfile(source, destination)
        if destination.stat().st_size != BYTES_280 or hashlib.sha256(destination.read_bytes()).hexdigest() != SHA256_280:
            destination.unlink()
            raise ValueError('280原生运行时附件身份不匹配')
        destination.chmod(0o755)
        return {'version': VERSION_280, 'source_version': version, 'asset': ASSET, 'sha256': SHA256_280, 'bytes': BYTES_280}
    source = source or os.environ.get('V3_NATIVE_RUNTIME_ASSET')
    if not source:
        raise ValueError('请先在本仓库准备293制品，并设置 V3_NATIVE_RUNTIME_ASSET')
    shutil.copyfile(source, destination)
    if destination.stat().st_size != BYTES or hashlib.sha256(destination.read_bytes()).hexdigest() != SHA256:
        destination.unlink()
        raise ValueError('原生运行时附件身份不匹配')
    destination.chmod(0o755)
    return {'version': VERSION, 'source_version': version, 'asset': ASSET, 'sha256': SHA256, 'bytes': BYTES}
