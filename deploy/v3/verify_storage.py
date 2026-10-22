"""以实际 Docker 和合成 CLI 验证原子安装、缓存收口与共享程序隔离。"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'orchestrator'))
from storage_maintenance import deduplicate_immutable_tree


FAKE_NPM = '''#!/usr/local/bin/python3
import json
import os
from pathlib import Path
import sys

prefix = Path(sys.argv[sys.argv.index('--prefix') + 1])
version = sys.argv[-1].rsplit('@', 1)[1]
cache = Path(os.environ['NPM_CONFIG_CACHE']) / '_cacache'
cache.mkdir(parents=True, exist_ok=True)
(cache / 'test-only-download').write_bytes(b'cache-only' * 1024)
if os.environ.get('FAKE_NPM_FAIL') == '1':
    raise SystemExit(42)
package = prefix / 'node_modules/@anthropic-ai/claude-code'
package.mkdir(parents=True)
observed = os.environ.get('FAKE_OUTPUT_VERSION', version)
note = os.environ.get('FAKE_PROGRAM_NOTE', 'original')
program = package / 'cli.js'
program.write_text('#!/bin/sh\\nprintf "%s\\\\n" "' + observed + ' (仅本地合成夹具)"\\n#' + note + ('x' * 1048576) + '\\n')
program.chmod(0o755)
(prefix / 'node_modules/.bin').mkdir()
(prefix / 'node_modules/.bin/claude').symlink_to('../@anthropic-ai/claude-code/cli.js')
(prefix / 'package.json').write_text(json.dumps({'dependencies': {'@anthropic-ai/claude-code': version}}))
(package / 'package.json').write_text(json.dumps({'name': '@anthropic-ai/claude-code', 'version': version}))
(prefix / 'package-lock.json').write_text(json.dumps({'lockfileVersion': 3, 'packages': {
    'node_modules/@anthropic-ai/claude-code': {'version': version, 'resolved': 'https://registry.npmjs.org/test-only.tgz',
    'integrity': 'sha512-' + ('A' * 86) + '=='}}}))
'''


def _run(image: str, cli: Path, fixtures: Path, *, flags: dict | None = None,
         account_user: bool = False) -> subprocess.CompletedProcess:
    name = 'v3-storage-verification-' + uuid.uuid4().hex
    arguments = ['docker', 'run', '--rm', '--pull=never', '--name', name,
        '--label', 'vibebench.storage-probe=' + name, '--network=none', '--read-only',
        '--cap-drop=ALL', '--security-opt=no-new-privileges', '--memory=384m', '--pids-limit=64',
        '--tmpfs', '/run/v3:rw,nosuid,nodev,size=16m', '--tmpfs', '/var/log:rw,nosuid,nodev,size=16m',
        '--tmpfs', '/tmp:rw,nosuid,nodev,size=32m', '--tmpfs', '/root:rw,nosuid,nodev,size=16m',
        '--volume', str(cli) + (':/cli:ro' if account_user else ':/cli:rw'),
        '--volume', str(fixtures) + ':/fake:ro',
        '--volume', str(ROOT / 'images/account/cli-version.sh') + ':/verification/cli-version.sh:ro']
    if account_user:
        script = "from pathlib import Path\nimport errno\nimport json\np=Path('/cli/2.1.293/node_modules/@anthropic-ai/claude-code/cli.js')\nreadable=bool(p.read_bytes())\ntry:\n p.write_bytes(b'modified')\nexcept OSError as error:\n if error.errno not in (errno.EACCES,errno.EPERM,errno.EROFS):\n  raise\n print(json.dumps({'readable':readable,'write_denied':True}))\nelse:\n raise SystemExit('写入边界失效')\n"
        arguments.extend(['--user', '1000:1000', '--entrypoint', 'python3', image, '-B', '-c', script])
    else:
        arguments.extend(['--env', 'PATH=/fake:/usr/local/bin:/usr/bin:/bin'])
        for key, value in (flags or {}).items():
            arguments.extend(['--env', key + '=' + value])
        wrapper = '/bin/bash /verification/cli-version.sh 2.1.293\nverification_status=$?\nif [ "$verification_status" -ne 0 ]; then cat /var/log/v3-cli-install.log >&2; fi\nexit "$verification_status"'
        arguments.extend(['--entrypoint', '/bin/bash', image, '-c', wrapper])
    try:
        return subprocess.run(arguments, capture_output=True, text=True, timeout=60)
    finally:
        inspected = subprocess.run(['docker', 'inspect', '--format',
            '{{index .Config.Labels "vibebench.storage-probe"}}', name], capture_output=True, text=True, timeout=15)
        if inspected.returncode == 0 and inspected.stdout.strip() == name:
            subprocess.run(['docker', 'rm', '-f', name], capture_output=True, check=True, timeout=30)


def main() -> None:
    """执行无外网、无真实账号的存储验收，结果写入全新文件。@return None。"""
    parser = argparse.ArgumentParser(description='v3 原子安装与静态制品隔离验证')
    parser.add_argument('--account-image', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('验证结果必须写入全新路径')
    image = json.loads(subprocess.check_output(['docker', 'image', 'inspect', args.account_image], text=True))[0]
    labels = image['Config'].get('Labels') or {}
    if labels.get('vibebench.product') != 'v3' or labels.get('vibebench.role') != 'account':
        raise ValueError('需要已有的 v3 账号镜像，不自动下载镜像')
    checks = {}
    result = {'status': 'running', 'actual_docker': True, 'synthetic_cli': True, 'network': 'none',
        'real_accounts': 0, 'real_model_calls': 0, 'image': image['Id'],
        'cli_script_sha256': hashlib.sha256((ROOT / 'images/account/cli-version.sh').read_bytes()).hexdigest(), 'checks': checks}
    try:
        with tempfile.TemporaryDirectory(prefix='v3-storage-verification-') as temporary:
            root = Path(temporary)
            fixtures = root / 'fixtures'
            fixtures.mkdir()
            (fixtures / 'npm').write_text(FAKE_NPM)
            (fixtures / 'npm').chmod(0o755)
            accounts = []
            for name in ('account-a', 'account-b'):
                cli = root / name
                cli.mkdir()
                completed = _run(args.account_image, cli, fixtures)
                if completed.returncode:
                    raise ValueError('合成 CLI 首次安装失败：' + completed.stderr[-2000:])
                version = cli / '2.1.293'
                if not (version / '.ready').is_file() or (cli / '.npm-cache/_cacache').exists():
                    raise ValueError('安装完成标记或缓存收口不符合契约')
                receipt = json.loads((version / '.v3-cli-install.json').read_text())
                if receipt['protocol'] != 2 or version.stat().st_mode & 0o777 != 0o755:
                    raise ValueError('安装回执或账号读取权限不正确')
                accounts.append(cli)
            checks['atomic_install_and_cache_cleanup'] = True
            program_a = accounts[0] / '2.1.293/node_modules/@anthropic-ai/claude-code/cli.js'
            program_b = accounts[1] / '2.1.293/node_modules/@anthropic-ai/claude-code/cli.js'
            for cli in accounts:
                deduplicate_immutable_tree(cli / '2.1.293', minimum_bytes=1024**2, owner_uid=0,
                    canonical_root=root / 'shared-programs')
            if program_a.stat().st_ino != program_b.stat().st_ino:
                raise ValueError('相同只读程序没有实现物理复用')
            checks['shared_program_inode'] = True
            sibling_bytes = program_b.read_bytes()
            sibling_inode = program_b.stat().st_ino
            orphan = accounts[1] / '.install-2.1.293.orphan01'
            orphan.mkdir()
            (orphan / 'partial-download').write_bytes(b'cache-only')
            completed = _run(args.account_image, accounts[1], fixtures, flags={'FAKE_NPM_FAIL': '1'})
            if completed.returncode != 0 or program_b.stat().st_ino != sibling_inode or orphan.exists():
                raise ValueError('已就绪版本不应重新下载或重装')
            checks['ready_reuse_without_download'] = True
            checks['abandoned_staging_collected'] = True
            cache = accounts[1] / '.npm-cache/_cacache'
            cache.mkdir(parents=True)
            (cache / 'test-only-cache').write_bytes(b'preserved-when-cleanup-fails')
            (fixtures / 'rm').write_text('#!/bin/sh\ncase "$*" in *_cacache*|*_logs*) exit 1;; esac\nexec /bin/rm "$@"\n')
            (fixtures / 'rm').chmod(0o755)
            try:
                completed = _run(args.account_image, accounts[1], fixtures, flags={'FAKE_NPM_FAIL': '1'})
                if completed.returncode != 0 or not cache.exists() or program_b.stat().st_ino != sibling_inode:
                    raise ValueError('缓存回收故障阻断了已验证的程序')
                checks['cache_cleanup_failure_keeps_ready_cli'] = True
            finally:
                (fixtures / 'rm').unlink()
            (accounts[0] / '2.1.293/.ready').unlink()
            completed = _run(args.account_image, accounts[0], fixtures, flags={'FAKE_NPM_FAIL': '1'})
            if completed.returncode != 42 or program_a.read_bytes() != sibling_bytes:
                raise ValueError('失败安装改写了旧版本')
            if list(accounts[0].glob('.install-*')) or (accounts[0] / '.npm-cache/_cacache').exists():
                raise ValueError('失败安装没有收口暂存和下载缓存')
            checks['failed_install_preserves_programs'] = True
            completed = _run(args.account_image, accounts[0], fixtures, flags={'FAKE_OUTPUT_VERSION': '9.9.9'})
            if completed.returncode != 3 or (accounts[0] / '2.1.293/.ready').exists():
                raise ValueError('错误版本被发布为可用')
            checks['wrong_version_not_published'] = True
            completed = _run(args.account_image, accounts[0], fixtures, flags={'FAKE_PROGRAM_NOTE': 'new-install'})
            if completed.returncode != 0 or program_a.read_bytes() == sibling_bytes:
                raise ValueError('独立重新安装没有发布新副本')
            if program_b.read_bytes() != sibling_bytes or program_b.stat().st_ino != sibling_inode:
                raise ValueError('重装污染了兄弟账号程序')
            checks['reinstall_preserves_sibling_inode_and_bytes'] = True
            completed = _run(args.account_image, accounts[1], fixtures, account_user=True)
            if completed.returncode != 0 or json.loads(completed.stdout) != {'readable': True, 'write_denied': True}:
                raise ValueError('UID1000 的只读挂载边界失效')
            checks['uid1000_readable_and_write_denied'] = True
        result['status'] = 'passed'
    except Exception as error:
        result.update(status='failed', error_type=type(error).__name__)
        raise
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with args.output.open('x') as output:
            json.dump(result, output, ensure_ascii=False, indent=2)
            output.write('\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
