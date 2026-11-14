"""在目标ABI构建并冻结恢复器工具与业务seccomp过滤器。"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess


class Comparison(ctypes.Structure):
    """libseccomp固定参数比较结构。"""
    _fields_ = [('arg', ctypes.c_uint), ('op', ctypes.c_int), ('a', ctypes.c_uint64), ('b', ctypes.c_uint64)]


def export_filter(profile: Path, output: Path) -> None:
    """从固定x64零能力画像生成内核过滤器。@param profile 冻结Docker规则。@param output 新BPF文件。@return 无。"""
    if platform.machine() != 'x86_64':
        raise ValueError('恢复器仅支持Linux x64')
    rules = json.loads(profile.read_text())
    if rules['defaultAction'] != 'SCMP_ACT_ERRNO' or rules['defaultErrnoRet'] != 1:
        raise ValueError('业务过滤器默认动作漂移')
    lib = ctypes.CDLL('libseccomp.so.2')
    lib.seccomp_init.argtypes, lib.seccomp_init.restype = [ctypes.c_uint32], ctypes.c_void_p
    lib.seccomp_release.argtypes = [ctypes.c_void_p]
    lib.seccomp_syscall_resolve_name.argtypes, lib.seccomp_syscall_resolve_name.restype = [ctypes.c_char_p], ctypes.c_int
    lib.seccomp_rule_add_array.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint, ctypes.POINTER(Comparison)]
    lib.seccomp_export_bpf.argtypes = [ctypes.c_void_p, ctypes.c_int]
    context = lib.seccomp_init(0x50001)
    if not context:
        raise ValueError('业务过滤器初始化失败')
    try:
        operations = {'SCMP_CMP_LT': 2, 'SCMP_CMP_EQ': 4, 'SCMP_CMP_MASKED_EQ': 7}
        for rule in rules['syscalls']:
            included = rule.get('includes', {})
            excluded = rule.get('excludes', {})
            if ('arches' in included and 'amd64' not in included['arches']) or 'amd64' in excluded.get('arches', []):
                continue
            if set(included) - {'arches', 'minKernel'} or set(excluded) - {'arches'}:
                raise ValueError('业务过滤器条件漂移')
            if included.get('minKernel', '4.8') != '4.8':
                raise ValueError('业务过滤器内核条件漂移')
            action = 0x7FFF0000 if rule['action'] == 'SCMP_ACT_ALLOW' else 0x50000 | rule['errnoRet']
            arguments = rule.get('args', [])
            comparisons = (Comparison * len(arguments))(*[
                Comparison(item['index'], operations[item['op']], item['value'], item.get('valueTwo', 0)) for item in arguments])
            for name in rule['names']:
                number = lib.seccomp_syscall_resolve_name(name.encode())
                # 当前libseccomp尚未命名的新系统调用继续沿默认拒绝，不扩大业务能力。
                if number == -1:
                    continue
                if lib.seccomp_rule_add_array(context, action, number, len(arguments), comparisons):
                    raise ValueError('业务过滤器规则生成失败')
        with output.open('xb') as content:
            if lib.seccomp_export_bpf(context, content.fileno()):
                raise ValueError('业务过滤器导出失败')
    finally:
        lib.seccomp_release(context)


def main() -> None:
    """构建目标系统产物及其完整SHA清单。@return 无。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    arguments = parser.parse_args()
    source, output = arguments.source.resolve(), arguments.out.resolve()
    frozen = json.loads((source / 'source-manifest.json').read_text())
    for name, digest in frozen.items():
        if Path(name).name != name or hashlib.sha256((source / name).read_bytes()).hexdigest() != digest:
            raise ValueError('恢复器构建来源漂移')
    output.mkdir(parents=True, exist_ok=False)
    # build.py在源码包内复用同一补丁；目标ABI构建避免跨系统动态库漂移。
    subprocess.run(['python3', str(source / 'build.py'), '--out', str(output / 'build'),
                    '--patch', str(source / 'memfd-executable.patch')], check=True)
    shutil.copyfile(output / 'build/criu', output / 'criu')
    os.chmod(output / 'criu', 0o755)
    for name in ('controller.py', 'diagnostics.py', 'entry.py', 'entropy.py', 'protocol.py', 'shared_image.py', 'supervisor.py', 'LICENSE.seccomp'):
        shutil.copyfile(source / name, output / name)
    shutil.copytree(output / 'build/licenses', output / 'licenses')
    subprocess.run(['cc', '-O2', '-Wall', '-Wextra', '-Werror', '-Wl,-z,relro,-z,now',
                    str(source / 'launch.c'), '-o', str(output / 'launch')], check=True)
    export_filter(source / 'seccomp.json', output / 'business-seccomp.bpf')
    profile = {'protocol': 1, 'entropy_profile': 'bun143-wipeonfork-v1',
        'image_sha256': '564019c9560e960e96875c9663975491534b27c789ea3d23e5c13309ff293c79',
        'image_bytes': 112843960, 'criu': json.loads((output / 'build/manifest.json').read_text()),
        'files': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in output.iterdir() if path.is_file()}}
    (output / 'profile.json').write_text(json.dumps(profile, sort_keys=True, indent=2) + '\n')
    shutil.rmtree(output / 'build')


if __name__ == '__main__':
    main()
