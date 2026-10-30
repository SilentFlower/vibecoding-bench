"""在禁网合成容器内重复切换真实监听，验证当前网络脚本与持久 CA。"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
from uuid import uuid4


def verify_inside(cycles: int) -> dict:
    """在测试容器中运行生产网络切换脚本，仅使用回环和合成来源。

    :param cycles: 抓包与透传的重复次数。
    :return: 模式切换和真实进程确认结果。
    """
    root = Path('/run/v3')
    root.chmod(0o700)
    (root / 'proxychains.conf').write_text('strict_chain\nproxy_dns\n[ProxyList]\nsocks5 127.0.0.1 1\n')
    spec = spec_from_loader('network_context', SourceFileLoader('network_context', '/usr/local/bin/v3-network-context'))
    if spec is None or spec.loader is None:
        raise RuntimeError('受测网络入口无法加载')
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    results = []
    steps = [('passthrough', '')]
    for index in range(cycles):
        namespace = 'projects' if index % 2 == 0 else 'warmup'
        steps.extend([('capture', f'{namespace}:' + 'a' * 32 + f':{index + 1}'), ('passthrough', '')])
    try:
        for index, (mode, source) in enumerate(steps):
            context = {'NETWORK_INSPECTION_MODE': mode, 'QUOTA_SOURCE': source}
            if mode == 'capture':
                flows = Path('/flows') / str(index)
                flows.mkdir()
                context.update(STATS_FILE=str(flows / 'stats.jsonl'), CAPTURE_FILE=str(flows / 'http_capture.jsonl'),
                    CAPTURE_INDEX_FILE=str(flows / 'capture_index.json'), CAPTURE_FULL_HTTP='1', SAVE_FULL_FLOWS='1',
                    CAPTURE_CONTEXT=json.dumps({'schema': 1, 'source': source, 'namespace': source.split(':')[0],
                        'work_id': 'a' * 32, 'claude_code_version': '2.1.293'}))
            (root / 'context.json').write_text(json.dumps(context))
            result = subprocess.run([sys.executable, '-B', '/usr/local/bin/v3-network-context'],
                text=True, capture_output=True, timeout=20)
            if result.returncode:
                raise RuntimeError('合成网络切换失败：' + result.stderr[-4000:])
            ack = json.loads((root / 'context-ack.json').read_text())
            if (ack['NETWORK_INSPECTION_MODE'] != mode or ack['QUOTA_SOURCE'] != source
                    or ack['process'] != ('recorder' if mode == 'capture' else 'passthrough')
                    or module._listener_identity(ack['pid']) is None or ack['previous_listener_graceful'] is not True):
                raise RuntimeError('实际监听身份或模式确认不匹配')
            if mode == 'capture' and not Path('/etc/mitm/mitmproxy-ca-cert.pem').is_file():
                raise RuntimeError('抓包 CA 未发布')
            results.append({'mode': mode, 'process': ack['process'], 'graceful': ack['previous_listener_graceful']})
    finally:
        module._terminate_listener(root / 'network.pid')
    return {'status': 'passed', 'cycles': cycles, 'switches': len(results),
        'external_network': 'none', 'model_requests': 0, 'results': results}


def verify_image(image: str, cycles: int) -> dict:
    """将当前受测脚本打包到一次性禁网容器，不挂账号或仓库私有配置。

    :param image: 已在本机存在的 v3 账号镜像。
    :param cycles: 重复次数。
    :return: 容器内验证结果及测试镜像身份。
    """
    inspected = json.loads(subprocess.check_output(['docker', 'image', 'inspect', image], text=True))[0]
    labels = inspected['Config'].get('Labels') or {}
    if labels.get('vibebench.product') != 'v3' or labels.get('vibebench.role') != 'account':
        raise ValueError('测试镜像必须为本地 v3 account 镜像')
    repository = Path(__file__).resolve().parents[2]
    name = 'bench-network-switch-' + uuid4().hex[:12]
    with tempfile.TemporaryDirectory(prefix='v3-network-switch-') as temporary:
        bundle = Path(temporary)
        files = {'network-context.py': repository / 'images/account/network-context.py',
            'passthrough.py': repository / 'images/account/passthrough.py',
            'runtime_files.py': repository / 'orchestrator/runtime_files.py',
            'runtime_diagnostics.py': repository / 'orchestrator/runtime_diagnostics.py',
            'verify.py': Path(__file__)}
        for target, source in files.items():
            shutil.copy2(source, bundle / target)
            (bundle / target).chmod(0o700 if target in ('network-context.py', 'passthrough.py') else 0o644)
        shutil.copytree(repository / 'images/sidecar', bundle / 'sidecar', ignore=shutil.ignore_patterns('__pycache__'))
        command = ['docker', 'run', '--rm', '--init', '--name', name, '--network', 'none', '--read-only',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--memory', '256m', '--memory-swap', '256m',
            '--pids-limit', '128', '--label', 'vibebench.verification=network-switch',
            '--mount', f'type=bind,src={bundle},dst=/fixture,readonly',
            '--mount', f'type=bind,src={bundle / "sidecar"},dst=/sidecar,readonly']
        for source, target in (('network-context.py', 'v3-network-context'), ('passthrough.py', 'v3-passthrough'),
                ('runtime_files.py', 'runtime_files.py'), ('runtime_diagnostics.py', 'runtime_diagnostics.py')):
            command.extend(['--mount', f'type=bind,src={bundle / source},dst=/usr/local/bin/{target},readonly'])
        for target, size in (('/run/v3', '16m'), ('/root', '64m'), ('/var/log', '32m'),
                ('/ca', '8m'), ('/etc/mitm', '8m'), ('/flows', '16m')):
            command.extend(['--tmpfs', f'{target}:rw,nosuid,nodev,size={size}'])
        for key, value in {'UPSTREAM_PROXY_SCHEME': 'socks5', 'UPSTREAM_SOCKS5_HOST': '127.0.0.1',
                'UPSTREAM_SOCKS5_PORT': '1', 'PROXYCHAINS_CONF_FILE': '/run/v3/proxychains.conf', 'TZ': 'UTC'}.items():
            command.extend(['--env', key + '=' + value])
        command.extend(['--entrypoint', 'python3', image, '-B', '/fixture/verify.py', '--inside', '--cycles', str(cycles)])
        try:
            result = subprocess.run(command, text=True, capture_output=True, timeout=30 + cycles * 40)
            if result.returncode:
                raise RuntimeError('禁网容器演练失败：' + result.stderr[-5000:])
            value = json.loads(result.stdout)
            value['base_image_id'] = inspected['Id']
            value['tested_source'] = 'current-worktree'
            value['source_sha256'] = {target: hashlib.sha256((bundle / target).read_bytes()).hexdigest()
                for target in files}
            value['sidecar_sha256'] = {target: hashlib.sha256((bundle / 'sidecar' / target).read_bytes()).hexdigest()
                for target in ('recorder.py', 'quota_protocol.py', 'tls_clienthello.py')}
            return value
        finally:
            subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> None:
    """解析验证参数并输出脱敏结果。:return: None；不连接真实代理或模型。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image')
    parser.add_argument('--cycles', type=int, default=3)
    parser.add_argument('--inside', action='store_true', help=argparse.SUPPRESS)
    arguments = parser.parse_args()
    if not 1 <= arguments.cycles <= 10 or not arguments.inside and not arguments.image:
        parser.error('需要本地 --image，cycles 必须为 1 到 10')
    value = verify_inside(arguments.cycles) if arguments.inside else verify_image(arguments.image, arguments.cycles)
    print(json.dumps(value, ensure_ascii=False))


if __name__ == '__main__':
    main()
