"""在实际账号角色中验证权限、秘密挂载与本地构建，不调用真实上游。"""
import json
import re


def verify_roles(cli, sender, network) -> dict:
    """核验真实 Docker 配置和业务身份，任何边界失效立即失败。

    :param cli: 本次合成账号 CLI 容器。
    :param sender: 同环境发送器。
    :param network: 同环境网络角色。
    :return: 可公开的实际权限与资源摘要。
    """
    facts = {}
    probe = '''import json,os,pathlib
status=dict(line.split(':',1) for line in pathlib.Path('/proc/self/status').read_text().splitlines() if ':' in line)
print(json.dumps({'uid':os.getuid(),'caps':{key:status[key].strip() for key in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb','NoNewPrivs')},'hostname':pathlib.Path('/proc/sys/kernel/hostname').read_text().strip(),'machine_id':pathlib.Path('/etc/machine-id').read_text().strip()}))
'''
    for role, container, uid in (('cli', cli, 1000), ('sender', sender, 1001)):
        container.reload()
        settings = container.attrs['HostConfig']
        assert settings['ReadonlyRootfs'] and settings['CapDrop'] == ['ALL']
        assert 'no-new-privileges:true' in settings['SecurityOpt']
        assert not settings.get('Devices') and settings['NetworkMode'] == 'container:' + network.id
        result = container.exec_run(['python3', '-I', '-c', probe])
        assert result.exit_code == 0, role + ' 身份读取失败'
        observed = json.loads(result.output)
        assert observed['uid'] == uid and observed['caps']['NoNewPrivs'] == '1'
        assert all(value == '0000000000000000' for key, value in observed['caps'].items() if key != 'NoNewPrivs')
        assert container.exec_run(['touch', '/etc/isolation-must-fail']).exit_code != 0
        facts[role] = {**observed, 'memory': settings['Memory'], 'memory_swap': settings['MemorySwap']}
    assert facts['cli']['hostname'] == facts['sender']['hostname']
    assert facts['cli']['machine_id'] == facts['sender']['machine_id']
    secrets = '''import os,pathlib
for name in ('/run/v3/sender.json','/run/v3/network/context.json','/ca/mitmproxy-ca.pem'):
 assert not os.access(name,os.R_OK),name
assert not any(key.startswith('UPSTREAM_') or key=='V3_INTERNAL_TOKEN' for key in os.environ)
try: entries=list(pathlib.Path('/flows/api').iterdir())
except PermissionError:pass
else:assert entries==[]
'''
    checked = cli.exec_run(['python3', '-I', '-c', secrets])
    assert checked.exit_code == 0, checked.output.decode(errors='replace')[-1000:]
    assert cli.exec_run(['touch', '/run/v3/must-not-create']).exit_code != 0
    assert cli.exec_run(['ip', 'route', 'add', 'unreachable', '203.0.113.250/32']).exit_code != 0
    # Docker 内置 DNS 即使不在 resolv.conf 中也可能可达，必须单独验证拒绝。
    blocked = '''import socket
for family,address in ((socket.AF_INET,('127.0.0.11',53)),(socket.AF_INET6,('2606:4700:4700::1111',443))):
 with socket.socket(family,socket.SOCK_STREAM) as s:
  s.settimeout(1)
  try:s.connect(address)
  except OSError:pass
  else:raise AssertionError('绕过网络约束')
'''
    assert cli.exec_run(['python3', '-I', '-c', blocked]).exit_code == 0
    build = '''set -eu
work=$(mktemp -d "$HOME/isolation-build.XXXXXX")
trap 'rm -rf "$work"' EXIT
cd "$work"
printf 'int main(void){return 0;}\n' > main.c
cc main.c -o program
./program
mkdir dependency
printf '{"name":"local-isolation-package","version":"1.0.0"}\n' > dependency/package.json
printf '{"name":"local-isolation-work","version":"1.0.0"}\n' > package.json
npm install --offline --no-audit --no-fund ./dependency >/dev/null
'''
    assert cli.exec_run(['bash', '-c', build]).exit_code == 0
    pressure = '''import errno,json,pathlib,tempfile
limit=int(pathlib.Path('/sys/fs/cgroup/memory.max').read_text())
allocated=bytearray(min(limit//4,384*1024**2))
for index in range(0,len(allocated),4096):allocated[index]=1
with tempfile.NamedTemporaryFile(prefix='isolation-pressure-',dir='/tmp',buffering=0) as output:
 written=0
 try:
  for _ in range(145):
   written+=output.write(b'x'*1024**2)
 except OSError as error:
  assert error.errno==errno.ENOSPC
 else:raise AssertionError('临时盘没有有限上限')
 assert written<=128*1024**2
 print(json.dumps({'allocated':len(allocated),'tmp_written':written,'tmp_full_rejected':True}))
'''
    checked = cli.exec_run(['python3', '-I', '-c', pressure])
    assert checked.exit_code == 0, checked.output.decode(errors='replace')[-1000:]
    facts['pressure'] = json.loads(checked.output)
    cli.exec_run(['sleep', '90'], detach=True)
    assert cli.exec_run(['python3', '-I', '/usr/local/bin/v3-cli-control', 'stop']).exit_code == 0
    cli.reload()
    assert cli.status == 'running', '清理业务子进程不能杀掉 CLI PID1'
    for role, container in (('cli', cli), ('sender', sender), ('network', network)):
        container.reload()
        facts.setdefault(role, {})['oom_killed'] = container.attrs['State']['OOMKilled']
        peak = container.exec_run(['cat', '/sys/fs/cgroup/memory.peak'])
        if peak.exit_code == 0:
            facts[role]['memory_peak'] = int(peak.output.strip())
        assert not container.attrs['State']['OOMKilled'], role + ' 超出资源预算'
    return facts


def memory_peaks(cli, sender, network) -> dict:
    """读取真实角色 cgroup 峰值，不能用宿主或其他角色的 RSS 替代。

    :param cli: CLI 容器。
    :param sender: 发送器。
    :param network: 网络角色。
    :return: 各角色峰值与限制。
    """
    result = {}
    for role, container in (('cli', cli), ('sender', sender), ('network', network)):
        container.reload()
        peak = container.exec_run(['cat', '/sys/fs/cgroup/memory.peak'])
        assert peak.exit_code == 0 and not container.attrs['State']['OOMKilled']
        result[role] = {'peak': int(peak.output.strip()), 'limit': container.attrs['HostConfig']['Memory']}
        assert result[role]['peak'] <= result[role]['limit'], role + ' 超出原分配预算'
    return result


def verify_route_failure(cli, network, gateway: str) -> dict:
    """将本账号默认路由故障回退到桥网，确认过滤器仍丢弃直连包。

    :param cli: 本账号 CLI。
    :param network: 本账号网络角色。
    :param gateway: 实际 Docker 桥网关。
    :return: 默认拒绝规则实际增加的计数。
    """
    def dropped() -> int:
        """读取账号 OUTPUT 默认策略的内核计数。@return 丢包数。"""
        value = network.exec_run(['iptables', '-nvxL', 'OUTPUT'])
        assert value.exit_code == 0
        return int(re.search(rb'policy DROP (\d+) packets', value.output)[1])

    before = dropped()
    assert network.exec_run(['ip', 'route', 'replace', 'default', 'via', gateway, 'dev', 'eth0']).exit_code == 0
    try:
        probe = '''import socket
with socket.socket() as s:
 s.settimeout(1)
 try:s.connect(('203.0.113.254',443))
 except OSError:pass
 else:raise AssertionError('直连被放行')
'''
        assert cli.exec_run(['python3', '-I', '-c', probe]).exit_code == 0
        after = dropped()
        assert after > before, '必须由账号过滤器实际丢包，不能只以任意连接失败替代'
        return {'kernel_dropped_packets': after - before}
    finally:
        assert network.exec_run(['ip', 'route', 'replace', 'default', 'dev', 'tun0']).exit_code == 0


def verify_official_tools(cli, root, fixture, certificate) -> dict:
    """使用本地合成 SSE 驱动官方 CLI 的 Bash 工具，不发送真实模型请求。

    :param cli: 普通用户 CLI 角色。
    :param root: 本次账号的宿主环境目录。
    :param fixture: 本账号代理夹具目录。
    :param certificate: 仅本地夹具证书。
    :return: 实际 CLI 结果和工具产物摘要。
    """
    authority = root / 'public-ca' / 'verification-cli.crt'
    authority.write_bytes(certificate.read_bytes())
    authority.chmod(0o644)
    (fixture / 'cli-tools').touch()
    try:
        assert cli.exec_run(['mkdir', '-p', '/home/node/isolation-tools']).exit_code == 0
        result = cli.exec_run(['timeout', '--kill-after=5', '60', '/cli/2.1.293/node_modules/.bin/claude',
            '--bare', '--print', '--dangerously-skip-permissions', '--max-turns', '3',
            '--model', 'claude-sonnet-4-5-20250929', '--output-format', 'json', 'Run the local isolation tool fixture.'],
            workdir='/home/node/isolation-tools', environment={
                'ANTHROPIC_API_KEY': 'synthetic-local-fixture', 'ANTHROPIC_BASE_URL': 'https://api.anthropic.com',
                'NODE_EXTRA_CA_CERTS': '/etc/mitm/verification-cli.crt', 'SSL_CERT_FILE': '/etc/mitm/verification-cli.crt',
                'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC': '1'})
        assert result.exit_code == 0, '官方 CLI 本地工具夹具失败：' + result.output.decode(errors='replace')[-1000:]
        produced = (root / 'home/isolation-tools/official-cli-tool.txt').read_text().strip()
        assert produced == '1000', '工具未在普通用户身份执行'
        return {'official_cli': '2.1.293', 'tool_uid': int(produced), 'compiled_program': True, 'real_model': False}
    finally:
        (fixture / 'cli-tools').unlink(missing_ok=True)
        authority.unlink(missing_ok=True)
