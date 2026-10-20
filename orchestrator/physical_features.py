"""账号环境的只读物理特征、受限观察快照和保存值对照。"""
import json
import math
import os
from pathlib import Path
from stat import S_ISREG

from resource_budget import isolated_account_limits, memory_bytes


MAX_SNAPSHOT_BYTES = 64 * 1024
FEATURE_LABELS = {
    "runtime_type": "形态", "hostname": "主机名", "os": "操作系统", "kernel": "内核",
    "architecture": "架构", "cpu": "CPU 型号", "cpu_visible": "可见逻辑 CPU", "cpu_affinity": "可用 CPU 亲和性",
    "cpu_quota": "CLI CPU 配额", "memory_bytes": "CLI 容器 RAM 上限", "account_memory_bytes": "账号合计 RAM 预算",
    "root_disk": "根文件系统", "mac": "MAC", "manufacturer": "厂商", "product": "产品",
    "version": "产品版本", "family": "系列", "serial": "序列号", "uuid": "UUID",
    "shell": "Shell", "package_manager": "包管理器", "toolchain": "工具链", "timezone": "时区",
    "locale": "语言区域", "machine_id": "machine-id 是否存在",
}

PHYSICAL_FEATURES_PROBE = '''import json,os,platform,shutil,socket,sys
from pathlib import Path
sys.path.insert(0, '/usr/local/bin')
values = dict.fromkeys(''' + repr(tuple(FEATURE_LABELS)) + ''')
def read(path):
    """限制本地文件读取量，缺失字段保留未知。"""
    try:
        with open(path, 'r', encoding='utf-8') as stream:
            return stream.read(1048576).strip()
    except (OSError, UnicodeError):
        return None
values.update(runtime_type='docker' if Path('/.dockerenv').exists() else 'container',
    hostname=socket.gethostname(), kernel=os.uname().release, architecture=platform.machine(),
    cpu_visible=os.cpu_count(), timezone=os.environ.get('TZ'), locale=os.environ.get('LANG'),
    shell=os.environ.get('SHELL'), machine_id=Path('/etc/machine-id').is_file())
release = read('/etc/os-release') or ''
for line in release.splitlines():
    if line.startswith('PRETTY_NAME='):
        values['os'] = line.split('=',1)[1].strip('"')
cpu = read('/proc/cpuinfo') or ''
models = sorted(set(line.split(':',1)[1].strip() for line in cpu.splitlines()
    if ':' in line and line.split(':',1)[0].strip() == 'model name'))
values['cpu'] = ', '.join(models) or None
if hasattr(os, 'sched_getaffinity'):
    values['cpu_affinity'] = len(os.sched_getaffinity(0))
quota = (read('/sys/fs/cgroup/cpu.max') or '').split()
if len(quota)==2 and quota[1].isdecimal() and int(quota[1])>0:
    if quota[0]=='max':
        values['cpu_quota']='未限制'
    elif quota[0].isdecimal():
        values['cpu_quota']=f'{int(quota[0])/int(quota[1]):g} 核'
try:
    from process_metrics import memory_limit
    values['memory_bytes']=memory_limit()
except (ImportError, OSError, ValueError):
    pass
for line in (read('/proc/mounts') or '').splitlines():
    parts=line.split()
    if len(parts)>2 and parts[1]=='/':
        values['root_disk']=parts[2]
        break
addresses=[]
for interface in Path('/sys/class/net').iterdir():
    if interface.name!='lo':
        address=read(interface/'address')
        if address:
            addresses.append(address)
values['mac']=', '.join(sorted(set(addresses))) or None
for key,name in {'manufacturer':'sys_vendor','product':'product_name','version':'product_version',
        'family':'product_family','serial':'product_serial','uuid':'product_uuid'}.items():
    values[key]=read('/sys/class/dmi/id/'+name)
values['package_manager']=', '.join(name for name in ('apt','apk','dnf','yum','pacman') if shutil.which(name)) or None
values['toolchain']=', '.join(name for name in ('python3','node','perl','gcc','git') if shutil.which(name)) or None
print(json.dumps({'schema':1, 'values':values}))
'''


def validate_features(payload: object) -> dict:
    """校验探针白名单及有界标量，拒绝未知字段或损坏类型。

    :param payload: 本地探针解码后的对象。
    :return: 可安全保存的物理字段。
    """
    if not isinstance(payload, dict) or set(payload) != {"schema", "values"} \
            or type(payload["schema"]) is not int or payload["schema"] != 1:
        raise ValueError("物理特征采集版本无效")
    values = payload["values"]
    if not isinstance(values, dict) or set(values) != set(FEATURE_LABELS):
        raise ValueError("物理特征字段不完整")
    integers = {"cpu_visible", "cpu_affinity", "memory_bytes", "account_memory_bytes"}
    for key, value in values.items():
        if value is None:
            continue
        if key == "machine_id":
            valid = type(value) is bool
        elif key in integers:
            valid = type(value) is int and 0 <= value < 2 ** 53
        else:
            valid = isinstance(value, str) and 0 < len(value) <= 512 and not any(ord(c) < 32 for c in value)
        if not valid:
            raise ValueError("物理特征字段格式无效")
    return values


def configured_features(row: dict) -> dict:
    """映射已固化的白名单配置，不为显示补齐或生成身份。

    :param row: 持久环境行，可包含已解码的 fingerprint。
    :return: 与实测字段同名的保存配置。
    """
    fingerprint = row.get("fingerprint") or json.loads(row["fingerprint_json"])
    system = fingerprint.get("system_profile")
    system = system if isinstance(system, dict) else {}
    computer = fingerprint.get("computer_profile")
    dmi = computer.get("dmi") if isinstance(computer, dict) else {}
    dmi = dmi if isinstance(dmi, dict) else {}
    values = {"hostname": fingerprint.get("hostname"), "mac": fingerprint.get("mac"),
        "timezone": fingerprint.get("tz"), "locale": fingerprint.get("lang"),
        "kernel": system.get("kernel_release"), "cpu": system.get("cpu_model_name"),
        "machine_id": bool(fingerprint.get("machine_id"))}
    values.update({key: dmi.get(key) for key in ("manufacturer", "product", "version", "family", "serial", "uuid")})
    try:
        values["account_memory_bytes"] = memory_bytes(fingerprint["mem"])
        values["memory_bytes"] = (isolated_account_limits(fingerprint["mem"], fingerprint.get("swap", "0"))["cli"][0]
            if row.get("isolation_version") == 2 else values["account_memory_bytes"])
    except (KeyError, TypeError, ValueError):
        # 配置缺失只影响展示，不能为了得到资源值重建环境或伪造宿主总内存。
        pass
    return values


def physical_features_summary(row: dict, path: Path, now: float) -> dict:
    """读取已有观察并逐字段对照配置，列表读取不执行容器命令。

    :param row: 当前持久环境行。
    :param path: root 私有观察文件。
    :param now: 当前 UTC 秒。
    :return: 来源、观察时间和配置/实测对照；损坏快照只返回固定错误摘要。
    """
    snapshot, message, status = None, "尚未采集容器实测", "missing"
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not S_ISREG(metadata.st_mode) or metadata.st_size > MAX_SNAPSHOT_BYTES:
                raise ValueError("物理特征快照无效")
            saved = json.loads(stream.read(MAX_SNAPSHOT_BYTES + 1))
        if not isinstance(saved, dict) or set(saved) != {"schema", "environment_id", "generation", "container_id", "observed_at", "values"}:
            raise ValueError("物理特征快照无效")
        validate_features({"schema": saved["schema"], "values": saved["values"]})
        if saved["environment_id"] != row["environment_id"] or type(saved["generation"]) is not int \
                or not isinstance(saved["container_id"], str) or not saved["container_id"] \
                or type(saved["observed_at"]) not in (int, float) or not math.isfinite(saved["observed_at"]) \
                or not 0 < saved["observed_at"] <= now + 60:
            raise ValueError("物理特征快照归属或时间无效")
        snapshot = saved
        status = "cached" if saved["generation"] == row["generation"] and saved["container_id"] == row.get("container_id") else "stale"
        message = "上次容器实测；刷新可重新采集" if status == "cached" else "旧容器代次的观察，请在环境空闲时重新采集"
    except FileNotFoundError:
        pass
    except (OSError, ValueError, TypeError, KeyError):
        message, status = "物理特征快照不可读取，请在环境空闲时重新采集", "invalid"
    configured = configured_features(row)
    observed = snapshot["values"] if snapshot else {}
    fields = []
    for key, label in FEATURE_LABELS.items():
        expected, actual = configured.get(key), observed.get(key)
        field_status = ("stale" if status == "stale" else "unobserved") if actual is None or status == "stale" else (
            "observed" if expected is None else "match" if actual == expected else "mismatch")
        fields.append({"key": key, "label": label, "configured": expected, "observed": actual, "status": field_status})
    return {"status": status, "message": message, "observed_at": snapshot["observed_at"] if snapshot else None,
        "generation": snapshot["generation"] if snapshot else None, "fields": fields}
