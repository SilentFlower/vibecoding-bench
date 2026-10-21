"""仅创建和精确清理本研究命名的隔离容器，不操作已有账号环境。"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import uuid
from pathlib import Path


def main() -> None:
    """启动一次研究并保留原始命令、日志与退出事实。

    :return: 无；退出结果与容器内部必要验证结果一致。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('baseline', 'reference'))
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    draft = root.parents[1] / 'content-drafts/pydantic-settings'
    name = 'bench-scenario-research-ps-' + arguments.mode + '-' + uuid.uuid4().hex[:8]
    evidence = root / 'evidence' / name
    evidence.mkdir()
    os.chown(evidence, 1000, 1000)
    command = ['docker', 'create', '--name', name, '--network', 'none', '--user', '1000:1000',
        '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
        '--memory', '1024m', '--memory-swap', '1024m', '--pids-limit', '128',
        '--tmpfs', '/work:rw,exec,nosuid,nodev,size=1536m,mode=1777',
        '--tmpfs', '/tmp:rw,nosuid,nodev,size=256m,mode=1777',
        '--mount', f'type=bind,source={draft / "seed"},target=/source,readonly',
        '--mount', f'type=bind,source={draft / "verification"},target=/control,readonly',
        '--mount', f'type=bind,source={root},target=/offline,readonly',
        '--mount', f'type=bind,source={root / "runner"},target=/runner,readonly',
        '--mount', f'type=bind,source={evidence},target=/evidence',
        '--label', 'vibebench.scenario-research=pydantic-settings',
        '--label', 'vibebench.scenario-research-owner=' + name,
        '--entrypoint', 'python3', 'vibebench-v3-account:v3-project-repairs-local-20261021-e',
        '-I', '-B', '/runner/run.py', arguments.mode]
    (evidence / 'create-command.json').write_text(json.dumps(command, ensure_ascii=False, indent=2) + '\n')
    identifier = None
    started = time.monotonic()
    result = {'name': name, 'mode': arguments.mode, 'evidence': str(evidence)}
    try:
        identifier = subprocess.check_output(command, text=True).strip()
        result['container_id'] = identifier
        (evidence / 'container-id.txt').write_text(identifier + '\n')
        with (evidence / 'container.log').open('wb') as stream:
            completed = subprocess.run(['docker', 'start', '-a', identifier], stdout=stream,
                stderr=subprocess.STDOUT, timeout=600)
        result['attach_exit_code'] = completed.returncode
        inspected = json.loads(subprocess.check_output(['docker', 'inspect', identifier]))[0]
        result.update(image_id=inspected['Image'], state=inspected['State'],
            constraints={key: inspected['HostConfig'][key] for key in
                ('NetworkMode', 'Memory', 'MemorySwap', 'PidsLimit', 'ReadonlyRootfs', 'CapDrop', 'SecurityOpt', 'Tmpfs')})
    except subprocess.TimeoutExpired:
        result['controller_timeout'] = True
    finally:
        result['elapsed_sec'] = round(time.monotonic() - started, 6)
        if identifier:
            inspected = json.loads(subprocess.check_output(['docker', 'inspect', identifier]))[0]
            labels = inspected['Config'].get('Labels') or {}
            if inspected['Name'] != '/' + name or labels.get('vibebench.scenario-research-owner') != name:
                raise ValueError('容器归属不符，拒绝扩大清理范围')
            result['remove_exit_code'] = subprocess.run(['docker', 'rm', '-f', identifier],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE).returncode
        (evidence / 'controller-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result.get('state', {}).get('ExitCode') == 0 and result.get('remove_exit_code') == 0 else 1)


if __name__ == '__main__':
    main()
