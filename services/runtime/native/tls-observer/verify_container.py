"""用正式账号候选镜像执行权限、容量和握手隔离验收。"""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
from uuid import uuid4


def main() -> None:
    """执行零真实模型的网络隔离容器。@return None；失败保留日志与实际容器状态。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', required=True)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    args.output.mkdir(parents=True, exist_ok=True)
    name = 'ccrb-tls-verify-' + uuid4().hex
    with tempfile.TemporaryDirectory() as folder:
        directory = Path(folder)
        sender = directory / 'sender'
        sender.write_text('#!/usr/local/bin/python3\n' + (source / 'verify_sender.py').read_text())
        sender.chmod(0o755)
        config = directory / 'sender.json'
        config.write_text(json.dumps({'native': {'max_workers': 6}}))
        command = ['docker', 'run', '--name', name, '--network', 'none', '--read-only', '--user', '0:0',
            '--cap-drop', 'ALL', '--cap-add', 'SYS_ADMIN', '--cap-add', 'SETUID', '--cap-add', 'SETGID',
            '--security-opt', 'no-new-privileges:true', '--security-opt', 'seccomp=' + str(source / 'seccomp.json'),
            '--memory', '1536m', '--memory-swap', '1536m', '--pids-limit', '256',
            '--tmpfs', '/tmp:rw,nosuid,nodev,size=128m,mode=1777',
            '--tmpfs', '/run/ccrb-observer:rw,noexec,nosuid,nodev,size=1m,mode=0750',
            '-v', str(sender) + ':/usr/local/bin/account-sender:ro',
            '-v', str(config) + ':/run/v3/sender.json:ro',
            '-v', str(args.binary.resolve()) + ':/usr/local/bin/ccrb-runtime:ro',
            '--entrypoint', '/usr/local/bin/python3', args.image, '/opt/ccrb-tls-observer/broker.py']
        try:
            with (args.output / 'container.log').open('w') as log:
                result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=180)
            actual = json.loads(subprocess.check_output(['docker', 'inspect', name]))[0]
            state = {key: actual['State'][key] for key in ('ExitCode', 'OOMKilled', 'Status')}
            (args.output / 'state.json').write_text(json.dumps(state))
            if result.returncode:
                raise SystemExit('隔离验收失败，请查看安全合成日志及state.json')
            last = (args.output / 'container.log').read_text().strip().splitlines()[-1]
            value = json.loads(last)
            assert value['model_requests'] == 0 and value['parallel_complete'] == 6
            (args.output / 'result.json').write_text(json.dumps(value, indent=2) + '\n')
            print(json.dumps(value), flush=True)
        finally:
            subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == '__main__':
    main()
