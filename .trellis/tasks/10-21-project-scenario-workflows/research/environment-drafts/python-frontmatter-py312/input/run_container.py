"""在本次隔离容器内安装离线依赖并校准原版和参考修复。"""
from __future__ import annotations

import difflib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


OUTPUT = Path('/evidence')
WORK = Path('/work')
PYTHON = '/work/venv/bin/python'


def run_step(name: str, command: list[str], cwd: Path, *, root: Path | None = None) -> None:
    """调用独立测量进程执行一个阶段。

    @param name 阶段名。@param command 实际命令。@param cwd 工作目录。@param root 候选根。@return None。
    """
    environment = dict(os.environ)
    if root is not None:
        environment['PYTHONPATH'] = str(root / 'library') + os.pathsep + str(root / 'app')
        environment['PROJECT_CANDIDATE_ROOT'] = str(root)
    environment['PROJECT_ANSWER_FILE'] = '/input/consult_example.py'
    result = subprocess.run(['/usr/local/bin/python3', '/input/measure.py', '--name', name,
        '--cwd', str(cwd), '--timeout', '150', '--', *command], env=environment, check=False)
    if result.returncode:
        raise RuntimeError(name + ' 实际执行失败，详见对应原始日志')


def apply_reference(library: Path) -> None:
    """按逐字校验的参考 unified diff 生成临时修复副本。@param library 临时库。@return None。"""
    path = library / 'frontmatter/__init__.py'
    original = path.read_text(encoding='utf-8')
    before = '    return Post(content, handler, **metadata)\n'
    if original.count(before) != 1:
        raise ValueError('参考补丁固定前像不唯一')
    updated = original.replace(before, '    # 先传正文与实际处理器，再写元数据，避免合法业务键与构造形参冲突。\n'
        '    post = Post(content, handler)\n    post.metadata.update(metadata)\n    return post\n')
    generated = ''.join(difflib.unified_diff(original.splitlines(keepends=True), updated.splitlines(keepends=True),
        fromfile='a/frontmatter/__init__.py', tofile='b/frontmatter/__init__.py'))
    expected = Path('/input/repair.patch').read_text(encoding='utf-8')
    if generated != expected:
        raise ValueError('实际补丁与冻结参考 diff 不一致')
    path.write_text(updated, encoding='utf-8')
    (OUTPUT / 'applied-reference.patch').write_text(generated, encoding='utf-8')


def main() -> None:
    """真实运行全部阶段，任一基础设施失败中止，不输出 ready。@return None。"""
    Path('/tmp/fm-home').mkdir()
    OUTPUT.joinpath('runtime.json').write_text(json.dumps({'python': sys.version, 'executable': sys.executable,
        'platform': platform.platform(), 'machine': platform.machine(), 'uid': os.getuid(), 'gid': os.getgid()}, indent=2) + '\n')
    run_step('venv-create', ['/usr/local/bin/python3', '-m', 'venv', '/work/venv'], WORK)
    requirements = json.loads(Path('/offline/profile/profile.json').read_text())['requirements']
    run_step('offline-install', [PYTHON, '-m', 'pip', 'install', '--disable-pip-version-check', '--no-cache-dir',
        '--no-index', '--find-links=/offline/artifacts', '--no-deps', '--report=/evidence/install-report.json',
        *requirements], WORK)
    baseline, repaired = WORK / 'base', WORK / 'repaired'
    shutil.copytree('/source', baseline)
    shutil.copytree('/source', repaired)
    apply_reference(repaired / 'library')
    run_step('baseline-native', [PYTHON, '/input/pytest_runner.py', 'baseline'], baseline / 'library', root=baseline)
    run_step('original-business', [PYTHON, '/input/legacy_observe.py'], baseline, root=baseline)
    run_step('consult-business', [PYTHON, '/input/native_observe.py', 'consult'], baseline, root=baseline)
    run_step('shallow-business', [PYTHON, '/input/native_observe.py', 'shallow'], baseline, root=baseline)
    run_step('original-repair-target', [PYTHON, '/input/native_observe.py', 'repair'], baseline, root=baseline)
    run_step('reference-repair-target', [PYTHON, '/input/native_observe.py', 'repair'], repaired, root=repaired)
    run_step('reference-native', [PYTHON, '/input/pytest_runner.py', 'reference'], repaired / 'library', root=repaired)
    cgroup = {}
    for name in ['memory.peak', 'memory.max', 'pids.peak', 'pids.max']:
        path = Path('/sys/fs/cgroup') / name
        try:
            cgroup[name] = path.read_text().strip()
        except OSError as error:
            cgroup[name] = {'unavailable': type(error).__name__}
    OUTPUT.joinpath('cgroup-observation.json').write_text(json.dumps(cgroup, indent=2) + '\n')
    print('所有实际执行阶段已退出；通过与否仍由控制端独立对照 XML、节点与业务 JSON。', flush=True)


if __name__ == '__main__':
    main()
