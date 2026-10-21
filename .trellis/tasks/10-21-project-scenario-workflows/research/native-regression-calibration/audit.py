"""独立核对新 wrapper 的原始 XML、节点、Bash 父进程和反例。"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent
COUNTS = {'python-frontmatter': (67, 0, 0, 11), 'pydantic-settings': (1256, 5, 0, 0), 'typer': (1481, 22, 2, 0)}


def read(path: Path) -> object:
    """读取原始 JSON。@param path 路径。@return 数据。"""
    return json.loads(path.read_text())


def digest(value: object) -> str:
    """使用 wrapper 声明算法核对摘要。@param value 数据。@return SHA-256。"""
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()


def reconstruct_removed_doctests(directory: Path) -> dict:
    """独立重建删示例输入，确认测试使用的实现摘要确有变化。@return 反例证据。"""
    package = ROOT.parent / 'content-drafts/python-frontmatter/seed/library/frontmatter'
    files = {str(path.relative_to(package)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in package.rglob('*') if path.is_file()}
    removed = 0
    for relative in ['__init__.py', 'default_handlers.py']:
        source = (package / relative).read_text()
        tree = ast.parse(source)
        starts, total = [], 0
        for line in source.splitlines(keepends=True):
            starts.append(total)
            total += len(line)
        ranges = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if '>>>' in (ast.get_docstring(node, clean=False) or ''):
                    expression = node.body[0].value
                    ranges.append((starts[expression.lineno-1] + expression.col_offset,
                        starts[expression.end_lineno-1] + expression.end_col_offset))
        removed += len(ranges)
        for first, last in sorted(ranges, reverse=True):
            source = source[:first] + repr('候选删去原示例的覆盖反例。') + source[last:]
        ast.parse(source)
        files[relative] = hashlib.sha256(source.encode()).hexdigest()
    actual = read(directory / 'evidence/deleted-doctests-wrapper.json')['overlay']['implementation_digest']
    assert removed == 8 and digest(files) == actual
    return {'removed_docstrings': removed, 'reconstructed_digest_matches_actual_candidate': True,
        'implementation_digest': actual}


def audit(project: str) -> dict:
    """对单仓校准做完整证据对账。@param project 项目。@return 摘要。"""
    directory = ROOT / read(ROOT / 'latest.json')[project]
    container = read(directory / 'container.json')
    assert container['removed'] is True and container['exit_code'] == 0 and container['oom_killed'] is False
    assert container['image_id'] == 'sha256:d055c5f0035c8fb3f204ed97d6f774a38afdb3515f5503f7fa028adb6a5e908d'
    assert container['wrapper_sha256'] == hashlib.sha256((directory / 'input/native_regression.py').read_bytes()).hexdigest()
    profile = read(directory / 'input/profile.json')
    config = container['config']
    assert config['uid'] == '1000:1000' and config['network_mode'] == 'none' and config['read_only_root'] is True
    assert config['memory_bytes'] == profile['regression']['memory_mb'] * 1024 * 1024
    assert config['pids_limit'] == profile['regression']['pids_limit']
    assert ',exec,' in config['tmpfs']['/work']
    result = read(directory / 'evidence/calibration-result.json')
    assert result['status'] == 'passed' and result['uid'] == result['gid'] == 1000
    assert result['python'].startswith('3.12.15 ')
    contract = read(directory / 'evidence/contract.json')
    expected_passed, expected_skipped, expected_xfailed, doctests = COUNTS[project]
    expected_ids = {item['id'] for item in contract['nodes']}
    assert len(expected_ids) == expected_passed + expected_skipped + expected_xfailed
    steps = []
    for row in result['steps']:
        report = read(directory / 'evidence' / (row['step'] + '-wrapper.json'))
        assert row['matches_expected'] is True and report['status'] == row['expected_status']
        assert row['temporary_source_paths_remaining'] == 0
        assert report['collected'] == len(expected_ids) and report['strict_doctest_count'] == doctests
        states = [read(path) for path in (directory / 'evidence' / row['step']).glob('pytest-*.json')]
        collected = [state for state in states if state['collection']]
        assert collected and all({item['id'] for item in state['collection']} == expected_ids for state in collected)
        xml = ET.parse(directory / 'evidence' / row['step'] / 'junit.xml').getroot()
        xml_cases = list(xml.iter('testcase'))
        assert len(xml_cases) == len(expected_ids)
        failure_count = len(list(xml.iter('failure')))
        error_count = len(list(xml.iter('error')))
        skipped_count = len(list(xml.iter('skipped')))
        if row['expected_status'] == 'passed':
            assert failure_count == error_count == 0
            assert skipped_count == expected_skipped + expected_xfailed
            assert report['counts']['passed'] == expected_passed
            assert report['counts']['skipped'] == expected_skipped and report['counts']['xfailed'] == expected_xfailed
            assert all(report['counts'][name] == 0 for name in ['failed', 'error', 'xpassed', 'unexecuted'])
        else:
            assert row['step'] == 'broken-source' and failure_count > 0
            assert report['returncode'] != 0 and report['counts']['failed'] > 0
        if project == 'typer':
            assert report['execution_command'][:4] == ['bash', '-c', '"$@"; result=$?; exit "$result"', 'bench-native']
            assert Path(report['processes']['master']['parent_executable']).name == 'bash'
            assert report['source_binding']['mode'] == 'private-venv-pure-path'
            assert report['source_binding']['path_target'] == report['cwd']
        for state in states:
            for imported in state['imports'].values():
                assert '/bench-native-regression-' in imported['path'] and '/project/' in imported['path']
        steps.append({'name': row['step'], 'status': report['status'], 'counts': report['counts'],
            'collected': report['collected'], 'doctests': doctests, 'elapsed_sec': report['elapsed_sec'],
            'collection_digest': report['collection_digest'], 'result_digest': report['result_digest'],
            'bash_parent': report.get('processes', {}).get('master', {}).get('parent_executable')})
    summary = {'project': project, 'status': 'passed', 'run_directory': str(directory.relative_to(ROOT)),
        'wrapper_sha256': container['wrapper_sha256'], 'image_id': container['image_id'], 'steps': steps,
        'resources': profile['regression'], 'cgroup': read(directory / 'evidence/cgroup.json'),
        'container_removed': True, 'docker_wait_max_sec': 1, 'model_executed': False}
    if project == 'python-frontmatter':
        summary['deleted_doctest_reconstruction'] = reconstruct_removed_doctests(directory)
    (directory / 'completion-audit.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    hashes = {str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob('*')) if path.is_file() and path.name != 'evidence-sha256.json'}
    (directory / 'evidence-sha256.json').write_text(json.dumps(hashes, ensure_ascii=False, indent=2) + '\n')
    return summary


def main() -> None:
    """审查显式项目，不运行任何测试。@return None。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('projects', nargs='+', choices=sorted(COUNTS))
    options = parser.parse_args()
    for project in options.projects:
        summary = audit(project)
        print(json.dumps({'project': project, 'status': summary['status'], 'steps': len(summary['steps']),
            'container_removed': summary['container_removed']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
