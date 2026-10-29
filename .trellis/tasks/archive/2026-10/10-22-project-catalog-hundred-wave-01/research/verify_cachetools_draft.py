"""通过真实产品原生验证器检查Cachetools草稿、参考和错误候选。"""
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


WORKSPACE = ROOT / '.deploy/project-catalog-hundred/stage-01'
IMAGE = 'ghcr.io/silentflower/vibebench-v3-account:v3-ci-39609484070-1'


def main() -> None:
    """核全部原版业务、修复正反例、完整回归及公开测试对照。

    :return: None。
    """
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, default=1)
    parser.add_argument('--case-prefix', default='')
    options = parser.parse_args()
    project = WORKSPACE / 'drafts/projects/cachetools'
    environment = WORKSPACE / 'drafts/environments/cachetools-py312'
    profile = json.loads((environment / 'profile/profile.json').read_text(encoding='utf-8'))
    manifest = json.loads((project / 'project.json').read_text(encoding='utf-8'))
    reference = WORKSPACE / 'references/cachetools'
    baseline_files, reference_files = _files(project / 'seed'), _files(reference)
    changed = {path for path in baseline_files.keys() | reference_files.keys()
        if baseline_files.get(path) != reference_files.get(path)}
    if changed != {'library/src/cachetools/_descriptor.py', 'library/tests/test_cachedmethod.py'}:
        raise ValueError('参考修改范围不符合授权')
    output = WORKSPACE / 'business/cachetools' / ('attempt-' + str(options.attempt).zfill(3))
    output.mkdir(parents=True, exist_ok=False)
    # 产品验证器分别挂载原版与冻结候选，同一路径作为字典键会覆盖/source挂载。
    frozen_original = output / 'original-candidate'
    copytree(project / 'seed', frozen_original)
    copyfile(Path(__file__).with_name('cachetools-public-test-observe.py'), project / 'verification/public_test_observe.py')
    specifications = {}
    cases = []
    for scene in manifest['scenarios']:
        for task in scene['tasks']:
            if 'native' not in task['evaluation']:
                continue
            native = json.loads((project / task['evaluation']['native']).read_text(encoding='utf-8'))
            specifications[task['id']] = native
            cases.append(('original-' + task['id'], native, frozen_original,
                'failed' if task['kind'] == 'modify' else 'passed', False))
    repair = specifications['CT-M01']
    cases.extend([('reference-CT-M01', repair, reference, 'passed', False),
        ('reference-full-regression', repair, reference, 'passed', True),
        ('wrong-hardcoded-self', repair, WORKSPACE / 'wrong-candidates/cachetools-hardcoded-self', 'failed', False)])
    public = {'script': 'verification/public_test_observe.py', 'args': [],
        'python_paths': ['library/src', 'app'], 'resource_profile': 'business',
        'expected': {'candidate_import': True, 'public_tests_passed': True,
            'counts': {'tests': 2, 'failed': 0, 'errors': 0, 'skipped': 0}, 'failures': []}}
    cases.extend([('public-tests-original', public, WORKSPACE / 'public-test-controls/cachetools-original', 'failed', False),
        ('public-tests-reference', public, reference, 'passed', False)])
    cases = [case for case in cases if case[0].startswith(options.case_prefix)]
    if not cases:
        raise ValueError('没有匹配的真实验证场景，不能将空集合记为通过')
    client = from_env()
    verifier = ProjectVerifier(client, WORKSPACE, WORKSPACE, IMAGE)

    def run(case: tuple) -> dict:
        """将单个真实程序结果与独立期望对账。@param case 场景定义。@return 实际结果。"""
        name, native, candidate, expected, regression = case
        started = time.monotonic()
        result = verifier.verify_native(candidate, project, native, environment, profile, regression=regression)
        report = {'case': name, 'expected': expected, 'expectation_met': result['status'] == expected,
            'elapsed_sec': round(time.monotonic() - started, 6), 'result': result, 'real_model_calls': 0}
        (output / (name + '.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return report

    results = []
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(run, case) for case in cases]
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                print(json.dumps({key: result[key] for key in ['case', 'expected', 'expectation_met', 'elapsed_sec']}, ensure_ascii=False), flush=True)
    finally:
        client.close()
    summary = {'cases': len(results), 'expectations_met': sum(item['expectation_met'] for item in results),
        'passed': all(item['expectation_met'] for item in results), 'reference_changed_paths': sorted(changed),
        'real_model_calls': 0, 'formal_catalog_modified': False}
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(0 if summary['passed'] else 1)


if __name__ == '__main__':
    main()
