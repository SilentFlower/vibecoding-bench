"""对独立原版、参考和反例调用真实原生验证器，统一保存逐项证据。"""
from __future__ import annotations

import json
import sys
import time
from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from shutil import copyfile, copytree

from docker import from_env


ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / 'orchestrator'))
from project_native_regression import _files
from project_verifier import ProjectVerifier


WORKSPACE = ROOT / '.deploy/project-catalog-hundred/stage-02'
IMAGE = 'ghcr.io/silentflower/vibebench-v3-account:v3-ci-39609484070-1'


def main() -> None:
    """验证只读或单工程目标草稿，不将原生成功当成正式准入。@return None。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--wrong')
    parser.add_argument('--public-count', type=int, default=0)
    parser.add_argument('--attempt', type=int, default=1)
    parser.add_argument('--case-prefix', default='')
    options = parser.parse_args()
    project = WORKSPACE / 'drafts/projects' / options.project
    manifest = json.loads((project / 'project.json').read_text(encoding='utf-8'))
    environment = WORKSPACE / 'drafts/environments' / manifest['environment']
    profile = json.loads((environment / 'profile/profile.json').read_text(encoding='utf-8'))
    tasks = [task for scene in manifest['scenarios'] for task in scene['tasks']]
    modifications = [task for task in tasks if task['kind'] == 'modify']
    if len(modifications) > 1:
        raise ValueError('多工程目标需要分别冻结独立参考，不能混用本入口')
    changed = set()
    if modifications:
        if not options.wrong or options.public_count < 1:
            raise ValueError('工程目标必须有错误候选和非空公开测试')
        modification = modifications[0]
        reference = WORKSPACE / 'references' / options.project
        original_files, reference_files = _files(project / 'seed'), _files(reference)
        changed = {path for path in original_files.keys() | reference_files.keys()
            if original_files.get(path) != reference_files.get(path)}
        if changed != set(modification['allowed_paths']):
            raise ValueError('参考实际文件集合与授权文件不一致')
    elif options.wrong or options.public_count:
        raise ValueError('只读项目不得伪造修改参考或公开修复测试')
    output = WORKSPACE / 'business' / options.project / ('attempt-' + str(options.attempt).zfill(3))
    output.mkdir(parents=True, exist_ok=False)
    controls = output / 'control-inputs'
    controls.mkdir()
    frozen_project = controls / 'project'
    copytree(project, frozen_project)
    (controls / 'environment-profile.json').write_text(json.dumps(profile, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    original = output / 'original-candidate'
    copytree(project / 'seed', original)
    if modifications:
        copyfile(Path(__file__).with_name(options.project + '-public-test-observe.py'),
            project / 'verification/public_test_observe.py')
        copyfile(project / 'verification/public_test_observe.py', frozen_project / 'verification/public_test_observe.py')
    specifications = {task['id']: json.loads((project / task['evaluation']['native']).read_text(encoding='utf-8'))
        for task in tasks if 'native' in task['evaluation']}
    cases = [("original-" + task['id'], specifications[task['id']], original,
        'failed' if task['kind'] == 'modify' else 'passed', False)
        for task in tasks if task['id'] in specifications]
    if modifications:
        repair = specifications[modification['id']]
        cases.extend([('reference-' + modification['id'], repair, reference, 'passed', False),
            ('reference-full-regression', repair, reference, 'passed', True),
            ('wrong-' + options.wrong, repair, WORKSPACE / 'wrong-candidates' / options.wrong, 'failed', False)])
        public = {'script': 'verification/public_test_observe.py', 'args': [],
            'python_paths': repair['python_paths'], 'resource_profile': 'business',
            'expected': {'candidate_import': True, 'public_tests_passed': True,
                'counts': {'tests': options.public_count, 'failed': 0, 'errors': 0, 'skipped': 0}, 'failures': []}}
        cases.extend([('public-tests-original', public,
            WORKSPACE / 'public-test-controls' / (options.project + '-original'), 'failed', False),
            ('public-tests-reference', public, reference, 'passed', False)])
    cases = [case for case in cases if case[0].startswith(options.case_prefix)]
    if not cases:
        raise ValueError('没有选中的验证路径')
    client = from_env()
    verifier = ProjectVerifier(client, WORKSPACE, WORKSPACE, IMAGE)

    def run(case: tuple) -> dict:
        """对一条真实结果核独立期望。@param case 场景。@return 逐项报告。"""
        name, native, candidate, expected, regression = case
        started = time.monotonic()
        result = verifier.verify_native(candidate, frozen_project, native, environment, profile, regression=regression)
        report = {'case': name, 'expected': expected, 'expectation_met': result['status'] == expected,
            'elapsed_sec': round(time.monotonic() - started, 6), 'result': result, 'real_model_calls': 0}
        (output / (name + '.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return report

    results = []
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            for future in as_completed([executor.submit(run, case) for case in cases]):
                report = future.result()
                results.append(report)
                print(json.dumps({key: report[key] for key in ('case', 'expected', 'expectation_met', 'elapsed_sec')},
                    ensure_ascii=False), flush=True)
    finally:
        client.close()
    summary = {'cases': len(results), 'expectations_met': sum(report['expectation_met'] for report in results),
        'passed': all(report['expectation_met'] for report in results),
        'reference_changed_paths': sorted(changed), 'real_model_calls': 0, 'formal_catalog_modified': False}
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(0 if summary['passed'] else 1)


if __name__ == '__main__':
    main()
