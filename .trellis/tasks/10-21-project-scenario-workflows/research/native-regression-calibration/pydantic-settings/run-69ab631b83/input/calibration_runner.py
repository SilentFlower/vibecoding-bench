"""只校准新统一 wrapper，不重复普通旧测试入口或调用模型。"""
from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


EVIDENCE = Path('/evidence')
WORK = Path('/work')
PYTHON = '/work/venv/bin/python'
PROFILE = json.loads(Path('/input/profile.json').read_text())
PROJECT = json.loads(Path('/input/request.json').read_text())['project']
TIMEOUT = PROFILE['regression']['timeout_sec']
RECORDS = []


def save(name: str, value: object) -> None:
    """保存本次真实证据。@param name 名称。@param value 数据。@return None。"""
    (EVIDENCE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def command_step(name: str, argv: list[str], cwd: Path) -> None:
    """执行准备命令并保留全部日志。@param name 名称。@param argv 数组。@param cwd 工作目录。@return None。"""
    started = time.monotonic()
    with (EVIDENCE / (name + '.log')).open('wb') as stream:
        result = subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
            timeout=max(180, TIMEOUT), check=False)
    record = {'step': name, 'command': argv, 'cwd': str(cwd), 'exit_code': result.returncode,
        'elapsed_sec': time.monotonic() - started}
    save(name + '-process.json', record)
    print(json.dumps(record, ensure_ascii=False), flush=True)
    if result.returncode:
        raise RuntimeError(name + ' 准备失败')


def wrapper_step(name: str, *, candidate: Path | None = None, freeze: bool = False,
                 expected: str = 'passed') -> None:
    """只通过新 wrapper 执行完整回归或对照。@return None。"""
    argv = [PYTHON, '/input/native_regression.py', '--project', PROJECT,
        '--baseline-root', '/baseline/library', '--evidence-dir', str(EVIDENCE / name),
        '--timeout-sec', str(TIMEOUT)]
    if freeze:
        argv.extend(['--freeze-baseline-contract', str(EVIDENCE / 'contract.json')])
    else:
        argv.extend(['--candidate-root', str(candidate), '--contract', str(EVIDENCE / 'contract.json')])
    started = time.monotonic()
    with (EVIDENCE / (name + '-wrapper.json')).open('wb') as stdout, (EVIDENCE / (name + '-wrapper.stderr')).open('wb') as stderr:
        completed = subprocess.run(argv, cwd=WORK, stdout=stdout, stderr=stderr, timeout=TIMEOUT + 90, check=False)
    result = json.loads((EVIDENCE / (name + '-wrapper.json')).read_text())
    temporary_paths = list(Path('/work/venv').glob('lib/python*/site-packages/_bench_native_source_*.pth'))
    record = {'step': name, 'command': argv, 'exit_code': completed.returncode,
        'elapsed_sec': time.monotonic() - started, 'expected_status': expected,
        'actual_status': result.get('status'), 'counts': result.get('counts'), 'collected': result.get('collected'),
        'strict_doctest_count': result.get('strict_doctest_count'),
        'collection_digest': result.get('collection_digest'), 'result_digest': result.get('result_digest'),
        'temporary_source_paths_remaining': len(temporary_paths),
        'matches_expected': completed.returncode == 0 and result.get('status') == expected and not temporary_paths}
    RECORDS.append(record)
    save('steps.json', RECORDS)
    print(json.dumps(record, ensure_ascii=False), flush=True)
    if not record['matches_expected']:
        raise RuntimeError(name + ' wrapper 结果与该对照的预期不符')


def remove_doctests(library: Path) -> None:
    """构造只删示例文档、不改业务代码的反例。@param library 临时库。@return None。"""
    for relative in ['frontmatter/__init__.py', 'frontmatter/default_handlers.py']:
        path = library / relative
        source = path.read_text()
        tree = ast.parse(source)
        lines = source.splitlines(keepends=True)
        starts, offset = [], 0
        for line in lines:
            starts.append(offset)
            offset += len(line)
        replacements = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc and '>>>' in doc:
                    expression = node.body[0].value
                    first = starts[expression.lineno - 1] + expression.col_offset
                    last = starts[expression.end_lineno - 1] + expression.end_col_offset
                    replacements.append((first, last))
        for first, last in sorted(replacements, reverse=True):
            source = source[:first] + repr('候选删去原示例的覆盖反例。') + source[last:]
        ast.parse(source)
        path.write_text(source)


def main() -> None:
    """真实执行每仓规定的新 wrapper 校准。@return None。"""
    WORK.joinpath('tmp').mkdir()
    Path('/tmp/regression-home').mkdir()
    command_step('venv-create', ['/usr/local/bin/python3', '-m', 'venv', '/work/venv'], WORK)
    command_step('offline-install', [PYTHON, '-m', 'pip', 'install', '--disable-pip-version-check', '--no-cache-dir',
        '--no-index', '--find-links=/offline/artifacts', '--no-deps', '--report=/evidence/install-report.json',
        *PROFILE['requirements']], WORK)
    wrapper_step('freeze-baseline', freeze=True)
    candidates = WORK / 'candidates'
    candidates.mkdir()
    original = candidates / 'original'
    shutil.copytree('/source', original)
    wrapper_step('original-candidate', candidate=original)
    if PROJECT in ('python-frontmatter', 'pydantic-settings'):
        reference = candidates / 'reference'
        shutil.copytree('/source', reference)
        patch = shutil.which('patch')
        if patch is None:
            raise RuntimeError('指定镜像缺少参考 unified diff 应用工具 patch')
        command_step('apply-reference', [patch, '--batch', '--forward', '-p1', '-i', '/input/reference.patch'],
            reference / 'library' if PROJECT == 'python-frontmatter' else reference)
        wrapper_step('reference-candidate', candidate=reference)
    if PROJECT == 'python-frontmatter':
        deleted = candidates / 'deleted-tests-and-hooks'
        shutil.copytree('/source', deleted)
        shutil.rmtree(deleted / 'library/tests')
        (deleted / 'library/conftest.py').write_text('raise RuntimeError("候选根 hook 不应执行")\n')
        (deleted / 'library/frontmatter/conftest.py').write_text('raise RuntimeError("候选包 hook 不应执行")\n')
        wrapper_step('deleted-tests-and-hooks', candidate=deleted)
        no_docs = candidates / 'deleted-doctests'
        shutil.copytree('/source', no_docs)
        remove_doctests(no_docs / 'library')
        wrapper_step('deleted-doctests', candidate=no_docs)
        broken = candidates / 'broken-source'
        shutil.copytree('/source', broken)
        path = broken / 'library/frontmatter/__init__.py'
        source = path.read_text()
        before = '        metadata.update(fm_data)\n'
        if source.count(before) != 1:
            raise ValueError('固定源码行为反例前像不唯一')
        path.write_text(source.replace(before, '        metadata.clear()\n'))
        wrapper_step('broken-source', candidate=broken, expected='failed')
    save('calibration-result.json', {'status': 'passed', 'project': PROJECT, 'steps': RECORDS,
        'python': sys.version, 'uid': os.getuid(), 'gid': os.getgid(), 'model_executed': False})


if __name__ == '__main__':
    status = 0
    try:
        main()
    except Exception as error:
        save('calibration-error.json', {'error_type': type(error).__name__, 'message': str(error), 'steps': RECORDS})
        print(type(error).__name__ + ': ' + str(error), flush=True)
        status = 1
    finally:
        measured = {}
        for name in ['memory.peak', 'memory.max', 'pids.peak', 'pids.max']:
            try:
                measured[name] = Path('/sys/fs/cgroup', name).read_text().strip()
            except OSError as error:
                measured[name] = {'unavailable': type(error).__name__}
        save('cgroup.json', measured)
    raise SystemExit(status)
