"""从真实原生结果生成逐仓准入记录，不将草稿或协议预检当正式准入。"""
from __future__ import annotations

from argparse import ArgumentParser
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path.cwd()
WORKSPACE = ROOT / '.deploy/project-catalog-hundred/stage-02'
RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'orchestrator'))
from project_library import snapshot_tree


def main() -> None:
    """只接受已真实全部满足期望的结果，保留原证据引用。@return None。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--baseline-index', type=Path, required=True)
    parser.add_argument('--attempt', type=int, default=1)
    parser.add_argument('--attempts', nargs='+', type=int)
    parser.add_argument('--additional-original', action='append', type=Path, default=[])
    options = parser.parse_args()
    project = WORKSPACE / 'drafts/projects' / options.project
    manifest = json.loads((project / 'project.json').read_text())
    source = json.loads((WORKSPACE / 'source-proofs' / (options.project + '.json')).read_text())
    baseline = next(row for row in json.loads(options.baseline_index.read_text())['projects'] if row['project'] == options.project)
    tasks = [task for scene in manifest['scenarios'] for task in scene['tasks']]
    modifications = [task for task in tasks if task['kind'] == 'modify']
    latest, history, summary = {}, [], None
    for attempt in sorted(set(options.attempts or [options.attempt])):
        directory = WORKSPACE / 'business' / options.project / ('attempt-' + str(attempt).zfill(3))
        summary_path = directory / 'summary.json'
        summary = json.loads(summary_path.read_text())
        paths = [path for path in sorted(directory.glob('*.json')) if path.name != 'summary.json']
        if len(paths) != summary['cases']:
            raise ValueError('实际结果文件与当轮汇总数量不一致')
        history.append({'attempt': attempt, 'summary': str(summary_path.relative_to(ROOT)),
            'sha256': hashlib.sha256(summary_path.read_bytes()).hexdigest(), 'passed': summary['passed']})
        for path in paths:
            row = json.loads(path.read_text())
            previous = latest.get(row['case'])
            if previous is not None and row['expected'] != previous['expected']:
                raise ValueError('重跑不能改写同一路径的独立期望')
            latest[row['case']] = {'case': row['case'], 'evidence': str(path.relative_to(ROOT)),
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'expectation_met': row['expectation_met'],
                'expected': row['expected'], 'actual_status': row['result']['status']}
    required = {'original-' + task['id'] for task in tasks if 'native' in task['evaluation']}
    if modifications:
        required.update({'reference-' + task['id'] for task in modifications})
        required.update({'reference-full-regression', 'public-tests-original', 'public-tests-reference'})
        wrong = {name for name in latest if name.startswith('wrong-')}
        if len(modifications) != 1 or len(wrong) != 1:
            raise ValueError('单目标工程必须有独立反例，不能混用未核参考')
        required.update(wrong)
    if set(latest) != required or not all(row['expectation_met'] is True
            and row['actual_status'] == row['expected'] for row in latest.values()):
        raise ValueError('全部必需业务路径尚未有同一期望的真实成功证据')
    evidence = [latest[name] for name in sorted(latest)]
    additional = []
    for path in options.additional_original:
        if modifications:
            raise ValueError('额外原版集合不能替代修改候选的累计回归')
        path = path.resolve(strict=True)
        if not path.is_relative_to(WORKSPACE / 'additional-native'):
            raise ValueError('额外原版证据必须来自本阶段独立验证')
        actual = json.loads(path.read_text())
        control = project / 'verification/native_additional_original.py'
        if (actual['project'] != options.project or actual['status'] != 'passed'
                or actual['native'].get('candidate_import') is not True or actual['oom_killed']
                or not actual['container_removed'] or actual['network'] != 'none'
                or actual['account_credentials_mounted']
                or actual['control_script_sha256'] != hashlib.sha256(control.read_bytes()).hexdigest()):
            raise ValueError('额外原版集合或隔离／清理不符')
        frozen_source = snapshot_tree(path.parent / 'candidate/library')['digest']
        if frozen_source != snapshot_tree(project / 'seed/library')['digest']:
            raise ValueError('额外入口并非当前完整固定源码')
        additional.append({'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'library_digest': frozen_source, 'collected': actual['native']['collected'],
            'passed': actual['native']['passed'], 'scope': '固定原版额外官方集合；不是可修改候选回归'})
    report = {'project': options.project, 'stage': 'native_verified_pending_mock',
        'source_commit': source['revision'], 'source_file_count': source['complete_tracked_files'],
        'license_files': manifest['source']['license_files'], 'scenarios': len(manifest['scenarios']),
        'unique_tasks': len(tasks), 'modify_tasks': len(modifications), 'non_modify_tasks': len(tasks) - len(modifications),
        'native_baseline': baseline, 'verified_unique_native_cases': len(evidence), 'native_evidence': evidence,
        'native_attempt_history': history,
        'additional_original_native': additional,
        'reference_changed_paths': summary['reference_changed_paths'], 'formal_registered': False,
        'mock_status': 'not_run', 'pending': ['真实产品链mock', '页面/API/数据库对账', 'Git/Docker交付'],
        'real_model_calls': 0, 'production_status': 'not_deployed', 'failed_attempts_retained': True,
        'scope': '完整原生与业务独立期望通过；产品链、页面及正式交付另验，不代表真实模型质量'}
    target = RESEARCH / (options.project + '-admission.json')
    if target.exists():
        raise ValueError('既有准入证据不覆盖')
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    (RESEARCH / (options.project + '-admission.md')).write_text('# ' + options.project + '原生业务准入记录\n\n固定源码' + source['revision']
        + '，完整' + str(source['complete_tracked_files']) + '个Git跟踪文件及实际许可保留。'
        + str(len(manifest['scenarios'])) + '场景／' + str(len(tasks)) + '独立任务，其中' + str(len(modifications))
        + '项修改；' + str(len(evidence)) + '条实际原生路径全部符合独立期望，完整基线与工程正反例见同名JSON和逐条原始结果。\n\n'
        + '当前尚待产品链、页面／API／数据库及Git／Docker准入，不作正式注册或真实模型效果声明。模型调用0，未推送或部署。\n')
    print(json.dumps({'project': options.project, 'tasks': len(tasks), 'native_cases': len(evidence),
        'status': 'native_verified_pending_mock'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
