"""固定账号的常规系统信息画像；不处理设备身份或真实资源指标。"""
import json
import re
import secrets


SYSTEM_PROFILE_VERSION = 1
SYSTEM_PROFILE_LABEL = 'vibebench.system-profile-version'
SYSTEM_PROFILE_DIRECTORY = '/etc/v3-system-profile'
SYSTEM_PROFILE_LIBRARY = '/usr/local/lib/v3-system-profile.so'
MAX_CPUINFO_BYTES = 4 * 1024 ** 2

# 模板只能追加，已有 ID 不得重新解释；完整来源见本任务 research/templates.md。
KERNEL_TEMPLATES = {
    'debian-6.1.0-31': ('6.1.0-31-amd64', '#1 SMP PREEMPT_DYNAMIC Debian 6.1.128-1 (2025-02-07)'),
    'debian-6.1.0-32': ('6.1.0-32-amd64', '#1 SMP PREEMPT_DYNAMIC Debian 6.1.129-1 (2025-03-06)'),
}
CPU_TEMPLATES = {
    'amd-naples-7301': (('AuthenticAMD', '23', '1'), 'AMD EPYC 7301 16-Core Processor'),
    'amd-naples-7351': (('AuthenticAMD', '23', '1'), 'AMD EPYC 7351 16-Core Processor'),
    'amd-naples-7401': (('AuthenticAMD', '23', '1'), 'AMD EPYC 7401 24-Core Processor'),
    'amd-naples-7451': (('AuthenticAMD', '23', '1'), 'AMD EPYC 7451 24-Core Processor'),
    'amd-cezanne-5800h': (('AuthenticAMD', '25', '80'), 'AMD Ryzen 7 5800H with Radeon Graphics'),
    'amd-cezanne-5900hx': (('AuthenticAMD', '25', '80'), 'AMD Ryzen 9 5900HX with Radeon Graphics'),
}
SYSTEM_PROFILE_PROBE = '''import json,os,pathlib
u=os.uname()
p=pathlib.Path('/etc/v3-system-profile')
cpu=pathlib.Path('/proc/cpuinfo').read_text()
print(json.dumps({'release':u.release,'version':u.version,
 'proc_version':pathlib.Path('/proc/version').read_text(),
 'sys_release':pathlib.Path('/proc/sys/kernel/osrelease').read_text(),
 'sys_version':pathlib.Path('/proc/sys/kernel/version').read_text(),
 'cpu_models':[line.split(':',1)[1].strip() for line in cpu.splitlines() if line.split(':',1)[0].strip()=='model name'],
 'readonly':not os.access(p,os.W_OK) and not os.access('/etc/ld.so.preload',os.W_OK)}))
'''


def cpu_signature(cpuinfo: str) -> tuple[str, str, str]:
    """核验所有逻辑 CPU 的代际一致且信息完整。

    :param cpuinfo: 实际 Docker 网络角色读到的原始 cpuinfo。
    :return: 厂商、十进制 family 和 model。
    """
    if not isinstance(cpuinfo, str) or not cpuinfo or len(cpuinfo.encode()) > MAX_CPUINFO_BYTES:
        raise ValueError('系统画像 CPU 信息缺失或过大')
    signatures = set()
    blocks = re.split(r'\n\s*\n', cpuinfo.strip())
    for block in blocks:
        fields = dict((key.strip(), value.strip()) for line in block.splitlines()
            if ':' in line for key, value in [line.split(':', 1)])
        if not all(fields.get(key) for key in ('processor', 'vendor_id', 'cpu family', 'model', 'model name')):
            raise ValueError('系统画像 CPU 字段缺失，不支持当前架构')
        if not all(fields[key].isdecimal() for key in ('processor', 'cpu family', 'model')):
            raise ValueError('系统画像 CPU 代际字段无效')
        signatures.add((fields['vendor_id'], fields['cpu family'], fields['model']))
    if len(signatures) != 1:
        raise ValueError('系统画像不支持混合 CPU 代际')
    return signatures.pop()


def _profile(kernel_id: str, cpu_id: str) -> dict:
    release, version = KERNEL_TEMPLATES[kernel_id]
    signature, model_name = CPU_TEMPLATES[cpu_id]
    # 内核三种常规表示成套保存，不把宿主编译时间混入随机 release。
    proc_version = (f'Linux version {release} (debian-kernel@lists.debian.org) '
        f'(gcc-12 (Debian 12.2.0-14) 12.2.0, GNU ld (GNU Binutils for Debian) 2.40) {version}\n')
    return {'schema': SYSTEM_PROFILE_VERSION, 'kernel_template_id': kernel_id,
        'kernel_release': release, 'kernel_version': version, 'proc_version': proc_version,
        'cpu_template_id': cpu_id, 'cpu_signature': list(signature), 'cpu_model_name': model_name}


def generate_system_profile(cpuinfo: str) -> dict:
    """在兼容候选中生成一次画像，调用方负责持久保存。

    :param cpuinfo: 当前 Docker 宿主的实际 CPU 信息。
    :return: 独立于设备身份的系统画像；不支持的代际明确拒绝。
    """
    signature = cpu_signature(cpuinfo)
    candidates = [key for key, (compatible, _) in CPU_TEMPLATES.items() if compatible == signature]
    if not candidates:
        raise ValueError('系统画像尚无当前 CPU 代际的兼容模板，请保留环境并补充核验')
    return _profile(secrets.choice(tuple(KERNEL_TEMPLATES)), secrets.choice(candidates))


def validate_system_profile(profile: dict, cpuinfo: str | None = None) -> dict:
    """验证固定模板及可选的实际 CPU 兼容性，不自动修复坏画像。

    :param profile: 已保存的 system_profile。
    :param cpuinfo: 可选的实际 CPU 文本，创建容器时必须提供。
    :return: 原画像；任何缺失、改写或代际冲突均抛出 ValueError。
    """
    if not isinstance(profile, dict) or type(profile.get('schema')) is not int \
            or profile['schema'] != SYSTEM_PROFILE_VERSION:
        raise ValueError('系统画像格式或版本无效，禁止重新随机')
    kernel_id, cpu_id = profile.get('kernel_template_id'), profile.get('cpu_template_id')
    if not isinstance(kernel_id, str) or not isinstance(cpu_id, str) \
            or kernel_id not in KERNEL_TEMPLATES or cpu_id not in CPU_TEMPLATES \
            or profile != _profile(kernel_id, cpu_id):
        raise ValueError('系统画像模板或内容损坏，禁止重新随机')
    if cpuinfo is not None and tuple(profile['cpu_signature']) != cpu_signature(cpuinfo):
        raise ValueError('系统画像与实际 CPU 代际冲突，需要核对迁移')
    return profile


def render_system_profile(profile: dict, cpuinfo: str) -> dict[str, str]:
    """渲染只读文件，CPU 原文只替换型号行。

    :param profile: 已持久化的合法画像。
    :param cpuinfo: 实际 CPU 原文，其余字段原样保留。
    :return: 固定文件名与内容，不含凭据或设备标识。
    """
    validate_system_profile(profile, cpuinfo)
    cpu = re.sub(r'(?m)^(model name\s*:\s*)[^\n]*',
        lambda match: match[1] + profile['cpu_model_name'], cpuinfo)
    return {'kernel-release': profile['kernel_release'] + '\n',
        'kernel-version': profile['kernel_version'] + '\n', 'proc-version': profile['proc_version'],
        'cpuinfo': cpu, 'ld.so.preload': SYSTEM_PROFILE_LIBRARY + '\n'}


def verify_system_profile(container, profile: dict) -> None:
    """核验 CLI 真实接口与只读边界，不用标签代替读取证据。

    :param container: 已启动的 CLI 角色。
    :param profile: 当前账号保存的画像。
    :return: None；覆盖不完整时明确报错。
    """
    validate_system_profile(profile)
    if container.labels.get(SYSTEM_PROFILE_LABEL) != str(SYSTEM_PROFILE_VERSION):
        raise ValueError('CLI 尚未启用系统画像，请空闲重建账号环境')
    result = container.exec_run(['python3', '-I', '-c', SYSTEM_PROFILE_PROBE])
    try:
        value = json.loads(result.output) if result.exit_code == 0 else None
    except (ValueError, TypeError):
        value = None
    expected = {'release': profile['kernel_release'], 'version': profile['kernel_version'],
        'proc_version': profile['proc_version'], 'sys_release': profile['kernel_release'] + '\n',
        'sys_version': profile['kernel_version'] + '\n', 'readonly': True}
    if not isinstance(value, dict) or any(value.get(key) != item for key, item in expected.items()) \
            or not isinstance(value.get('cpu_models'), list) or not value['cpu_models'] \
            or any(item != profile['cpu_model_name'] for item in value['cpu_models']):
        raise ValueError('CLI 系统画像实际读取或只读校验失败，需要检查环境')
