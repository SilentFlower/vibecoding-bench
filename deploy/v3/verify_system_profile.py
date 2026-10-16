"""真实 Docker 中验证系统画像覆盖与绕过边界，不调用真实上游。"""
import json
import shlex
import time
from pathlib import Path

from system_profile import validate_system_profile, verify_system_profile


def verify_system_information(cli, network, sender, fingerprint: dict) -> dict:
    """验证实际接口、动态/静态原生程序、线程和未覆盖路径。

    :param cli: 启用画像的 CLI。
    :param network: 同账号网络角色，提供未改写的内核基线。
    :param sender: 同账号发送器，应不加载覆盖。
    :param fingerprint: 已保存的账号画像。
    :return: 无凭据的覆盖结果；失败抛出异常。
    """
    profile = validate_system_profile(fingerprint['system_profile'])
    verify_system_profile(cli, profile)
    baseline = network.exec_run(['uname', '-r'])
    assert baseline.exit_code == 0
    real_release = baseline.output.decode().strip()
    for container in (network, sender):
        observed = container.exec_run(['cat', '/etc/ld.so.preload'])
        assert observed.exit_code == 0 and not observed.output.strip()
    source = Path(__file__).with_name('fixtures') / 'system_profile_probe.c'
    # 仅把本仓库的固定验证源码传入真实 CLI，路径由 mktemp 在账号 HOME 中产生。
    work = cli.exec_run(['mktemp', '-d', '/home/node/system-profile-check.XXXXXX'])
    assert work.exit_code == 0
    directory = work.output.decode().strip()
    try:
        script = "cat > " + shlex.quote(directory + '/probe.c') + " <<'V3_SYSTEM_PROFILE_SOURCE'\n" \
            + source.read_text() + '\nV3_SYSTEM_PROFILE_SOURCE\n'
        copied = cli.exec_run(['bash', '-c', script])
        assert copied.exit_code == 0
        for suffix, flags in (('dynamic', []), ('static', ['-static'])):
            compiled = cli.exec_run(['cc', '-O2', '-D_FORTIFY_SOURCE=2', '-Wall', '-Wextra', '-Werror', '-pthread', *flags,
                directory + '/probe.c', '-o', directory + '/probe-' + suffix])
            assert compiled.exit_code == 0, compiled.output.decode(errors='replace')
        started = time.monotonic()
        checked = cli.exec_run([directory + '/probe-dynamic', '--files'])
        assert checked.exit_code == 0, f'动态探针失败 {checked.exit_code}: {checked.output!r}'
        dynamic = json.loads(checked.output)
        checked = cli.exec_run([directory + '/probe-static'])
        assert checked.exit_code == 0
        static = json.loads(checked.output)
        assert dynamic['uname_release'] == profile['kernel_release']
        assert dynamic['syscall_release'] == static['uname_release'] == static['syscall_release'] == real_release
        assert dynamic['cpuid_brand'] == static['cpuid_brand']
        node = cli.exec_run(['node', '-e', '''const os=require('os'),fs=require('fs'),cp=require('child_process');
console.log(JSON.stringify({release:os.release(),cpu:os.cpus().map(x=>x.model),
 sys:fs.readFileSync('/proc/sys/kernel/osrelease','utf8'),
 proc:fs.readFileSync('/proc/version','utf8'),child:cp.execFileSync('uname',['-r'],{encoding:'utf8'})}));'''])
        assert node.exit_code == 0, node.output.decode(errors='replace')
        actual = json.loads(node.output)
        assert actual['release'] == profile['kernel_release']
        assert actual['sys'] == actual['child'] == profile['kernel_release'] + '\n'
        assert actual['proc'] == profile['proc_version']
        assert actual['cpu'] and all(value == profile['cpu_model_name'] for value in actual['cpu'])
        for path in ('/etc/ld.so.preload', '/etc/v3-system-profile/kernel-release', '/proc/cpuinfo'):
            assert cli.exec_run(['sh', '-c', 'echo changed > "$1"', 'sh', path]).exit_code != 0
        return {'schema': 1, 'kernel_template': profile['kernel_template_id'],
            'cpu_template': profile['cpu_template_id'], 'dynamic_files_threads_node_children': 'passed',
            'raw_syscall_static_cpuid': '真实值，未覆盖', 'readonly': True,
            'elapsed_seconds': round(time.monotonic() - started, 3)}
    finally:
        cli.exec_run(['rm', '-rf', directory])
