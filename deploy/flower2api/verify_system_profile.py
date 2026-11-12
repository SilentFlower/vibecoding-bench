"""真实 Docker 中验证系统画像覆盖与绕过边界，不调用真实上游。"""
import argparse
import json
import os
import shlex
import shutil
import tempfile
import time
import uuid
from pathlib import Path

from docker import from_env

from manage import inspect_images
from system_profile import (DMI_DIRECTORIES, DMI_FIELDS, validate_computer_profile, validate_system_profile,
    generate_computer_profile, generate_system_profile, render_computer_profile, render_system_profile,
    verify_computer_profile, verify_system_profile)


def verify_system_information(cli, network, sender, fingerprint: dict) -> dict:
    """验证实际接口、动态/静态原生程序、线程和未覆盖路径。

    :param cli: 启用画像的 CLI。
    :param network: 同账号网络角色，提供未改写的内核基线。
    :param sender: 同账号发送器，应不加载覆盖。
    :param fingerprint: 已保存的账号画像。
    :return: 无凭据的覆盖结果；失败抛出异常。
    """
    profile = validate_system_profile(fingerprint['system_profile'])
    computer = validate_computer_profile(fingerprint['computer_profile'], profile)
    verify_system_profile(cli, profile)
    verify_computer_profile(cli, computer, profile)
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
 proc:fs.readFileSync('/proc/version','utf8'),child:cp.execFileSync('uname',['-r'],{encoding:'utf8'}),
 dmi:Object.fromEntries(['/sys/class/dmi/id','/sys/devices/virtual/dmi/id'].map(dir=>[dir,
 Object.fromEntries(['sys_vendor','product_name','product_version','product_family','product_serial','product_uuid'].map(name=>{
 const path=dir+'/'+name; fs.accessSync(path,fs.constants.R_OK);
 let writable=true;try{fs.accessSync(path,fs.constants.W_OK)}catch{writable=false}
 return[name,{text:fs.readFileSync(path,'utf8'),exists:fs.existsSync(path),size:fs.statSync(path).size,writable}]}))]))}));'''])
        assert node.exit_code == 0, node.output.decode(errors='replace')
        actual = json.loads(node.output)
        assert actual['release'] == profile['kernel_release']
        assert actual['sys'] == actual['child'] == profile['kernel_release'] + '\n'
        assert actual['proc'] == profile['proc_version']
        assert actual['cpu'] and all(value == profile['cpu_model_name'] for value in actual['cpu'])
        expected = {directory: {name: {'text': computer['dmi'][key] + '\n', 'exists': True,
            'size': len((computer['dmi'][key] + '\n').encode()), 'writable': False} for key, name in DMI_FIELDS.items()}
            for directory in DMI_DIRECTORIES}
        assert actual['dmi'] == expected
        for path in ('/etc/ld.so.preload', '/etc/v3-system-profile/kernel-release', '/proc/cpuinfo'):
            assert cli.exec_run(['sh', '-c', 'echo changed > "$1"', 'sh', path]).exit_code != 0
        return {'schema': 1, 'kernel_template': profile['kernel_template_id'],
            'cpu_template': profile['cpu_template_id'], 'computer_template': computer['template_id'],
            'dynamic_files_threads_node_children': 'passed', 'dmi_content_metadata_access': 'passed',
            'libc_statx_and_syscall_passthrough': 'passed',
            'raw_syscall_static_cpuid': '真实值，未覆盖', 'readonly': True,
            'elapsed_seconds': round(time.monotonic() - started, 3)}
    finally:
        cli.exec_run(['rm', '-rf', directory])


def main() -> None:
    """在无 DMI 与预先存在 DMI 两种离线环境中验证真实原生接口。

    :return: None；验证失败抛出异常并清理本次专用容器。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    inspect_images({'V3_RELEASE_MANIFEST': str(args.manifest), **{
        'V3_' + role.upper() + '_IMAGE': manifest['images'][role]['reference'] for role in ('control', 'account')}})
    image = manifest['images']['account']['reference']
    client = from_env()
    deployment = 'computer-verify-' + uuid.uuid4().hex[:12]
    labels = {'vibebench.product': 'v3', 'vibebench.deployment': deployment, 'vibebench.role': 'verification'}
    containers = []
    with tempfile.TemporaryDirectory(prefix='v3-computer-profile-verify-') as temporary:
        root = Path(temporary)
        root.chmod(0o755)
        profile = root / 'profile'
        profile.mkdir(mode=0o755)
        cpuinfo = Path('/proc/cpuinfo').read_text()
        system = generate_system_profile(cpuinfo)
        computer = generate_computer_profile(system)
        fingerprint = {'system_profile': system, 'computer_profile': computer}
        for name, value in {**render_system_profile(system, cpuinfo), **render_computer_profile(computer, system)}.items():
            target = profile / name
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            target.write_text(value)
            target.chmod(0o444)
        fake_sys = root / 'sys'
        for directory in DMI_DIRECTORIES:
            target = fake_sys / directory.removeprefix('/sys/')
            target.mkdir(parents=True, mode=0o755)
            for name in DMI_FIELDS.values():
                (target / name).write_text('Synthetic Host Value\n')
                (target / name).chmod(0o444)
        try:
            baseline = client.containers.run(image, ['-I', '-c', 'import time; time.sleep(180)'],
                entrypoint='python3', detach=True, network_mode='none', read_only=True, cap_drop=['ALL'],
                security_opt=['no-new-privileges:true'], mem_limit='256m', pids_limit=64, labels=labels)
            containers.append(baseline)
            baseline.reload()
            for existing in (False, True):
                home = root / ('home-existing' if existing else 'home-default')
                home.mkdir(mode=0o755)
                os.chown(home, 1000, 1000)
                volumes = {str(profile): {'bind': '/etc/v3-system-profile', 'mode': 'ro'},
                    str(profile / 'ld.so.preload'): {'bind': '/etc/ld.so.preload', 'mode': 'ro'},
                    str(profile / 'cpuinfo'): {'bind': '/proc/cpuinfo', 'mode': 'ro'},
                    str(home): {'bind': '/home/node', 'mode': 'rw'}}
                if existing:
                    # 只在一次性验证容器模拟宿主已有 DMI；产品容器不替换 sysfs。
                    volumes[str(fake_sys)] = {'bind': '/sys', 'mode': 'ro'}
                cli = client.containers.run(image, ['-I', '-c', 'import time; time.sleep(180)'],
                    entrypoint='python3', detach=True, network_mode='none', read_only=True, cap_drop=['ALL'],
                    security_opt=['no-new-privileges:true'], user='1000:1000', mem_limit='512m', pids_limit=64,
                    tmpfs={'/tmp': 'rw,noexec,nosuid,nodev,size=32m'}, volumes=volumes, labels=labels)
                containers.append(cli)
                cli.reload()
                facts = verify_system_information(cli, baseline, baseline, fingerprint)
                print('通过：' + ('预先存在 DMI' if existing else '默认 sysfs') + ' 的原生读取与只读验证：'
                    + json.dumps(facts, ensure_ascii=False), flush=True)
                cli.remove(force=True)
                containers.remove(cli)
            broken = root / 'broken-profile'
            shutil.copytree(profile, broken)
            marker = broken / 'computer-profile-version'
            marker.chmod(0o644)
            marker.write_text('invalid\n')
            marker.chmod(0o444)
            invalid = client.containers.run(image, ['-I', '-c', 'import time; time.sleep(120)'],
                entrypoint='python3', detach=True, network_mode='none', read_only=True, cap_drop=['ALL'],
                security_opt=['no-new-privileges:true'], user='1000:1000', mem_limit='256m', pids_limit=32,
                volumes={str(broken): {'bind': '/etc/v3-system-profile', 'mode': 'ro'},
                    str(broken / 'ld.so.preload'): {'bind': '/etc/ld.so.preload', 'mode': 'ro'},
                    str(fake_sys): {'bind': '/sys', 'mode': 'ro'}}, labels=labels)
            containers.append(invalid)
            invalid.reload()
            try:
                verify_computer_profile(invalid, computer, system)
            except ValueError:
                refused = invalid.exec_run(['cat', '/sys/class/dmi/id/product_name'])
                assert refused.exit_code != 0 and b'Synthetic Host Value' not in refused.output
            else:
                raise AssertionError('损坏计算机画像未拒绝，可能回退到宿主身份')
            print('通过：损坏标记拒绝读取，未回退到预置宿主 DMI', flush=True)
        finally:
            for container in reversed(containers):
                container.remove(force=True)


if __name__ == '__main__':
    main()
