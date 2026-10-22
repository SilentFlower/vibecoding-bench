"""仅汇总29个可获取源码项目的真实本地证据，保留第30仓阻塞。"""
from __future__ import annotations

from argparse import ArgumentParser
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from subprocess import check_output
import sys


ROOT = Path.cwd()
RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'orchestrator'))
from project_library import ProjectLibrary


def read(path: Path) -> dict:
    """读取实际普通JSON。@param path 文件。@return JSON对象。"""
    assert path.is_file() and not path.is_symlink(), path
    return json.loads(path.read_text())


def evidence(path: Path) -> dict:
    """核普通证据并记录身份。@param path 原件。@return 路径及SHA。"""
    assert path.is_file() and not path.is_symlink(), path
    return {'path': str(path.relative_to(ROOT)), 'sha256': sha256(path.read_bytes()).hexdigest()}


def main() -> None:
    """要求29仓全部准入且最终交付一致后生成有限范围汇总。@return None。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--delivery', type=Path, required=True)
    options = parser.parse_args()
    output = RESEARCH / 'available-verification-summary.json'
    assert not output.exists(), '既有汇总不覆盖'
    inventory = read(RESEARCH.parent.parent / '10-22-project-catalog-hundred/research/inventory.json')
    source = read(RESEARCH / 'source-index.json')
    source_audit = read(RESEARCH / 'available-evidence-audit.json')
    native_summary = read(RESEARCH / 'available-native-summary.json')
    language = read(RESEARCH / 'available-content-language.json')
    library = ProjectLibrary(ROOT / 'project_library')
    delivery = read(options.delivery)
    assert delivery['status'] == 'passed' and delivery['catalog_digest'] == library.digest
    assert delivery['git_export']['status'] == delivery['docker_export']['status'] == 'passed'
    assert delivery['user_index_unchanged'] and not delivery['cleanup_errors']
    assert len(library.projects) == 99
    expected = {row['slug']: row for row in inventory['projects']}
    assert len(expected) == 100 and set(expected) - set(library.projects) == {'sqlglot'}
    keys = {row['slug'] for row in source['projects']} - {'sqlglot'}
    assert len(keys) == source_audit['verified_projects'] == native_summary['verified_projects'] == language['projects'] == 29
    assert {row['project'] for row in source_audit['items']} == keys
    for row in source_audit['items']:
        assert evidence(ROOT / row['source_proof']['path']) == row['source_proof']
    admissions, bundles, kinds = [], {}, Counter()
    primary, totals = Counter(), Counter()
    for key in sorted(keys):
        admission_path = RESEARCH / (key + '-admission.json')
        admission = read(admission_path)
        project = library.projects[key]
        assert admission['stage'] == 'formal_registered_local_verified'
        assert admission['formal_registered'] and admission['mock_status'] == 'passed' and not admission['pending']
        assert project.manifest['source']['commit'] == expected[key]['revision'] == admission['source_commit']
        assert project.manifest['source']['repository'] == expected[key]['repository']
        for row in admission['mock_evidence']:
            assert evidence(ROOT / row['path']) == row
        for row in admission['native_evidence']:
            assert evidence(ROOT / row['evidence'])['sha256'] == row['sha256']
            assert row['expectation_met'] and row['expected'] == row['actual_status']
        baseline = admission['native_baseline']
        assert evidence(ROOT / baseline['result'])['sha256'] == baseline['result_sha256']
        primary.update(baseline['counts'])
        totals.update(projects=1, scenarios=admission['scenarios'], tasks=admission['unique_tasks'],
            modify_tasks=admission['modify_tasks'], business_cases=admission['verified_unique_native_cases'],
            primary_native_main=baseline['main_collected'], subtests_separate=baseline['subtest_count'])
        for scene in project.manifest['scenarios']:
            kinds.update(task['kind'] for task in scene['tasks'])
        # 每个原件都来自正式准入时保存的唯一批次，失败重跑不重复计数。
        run_result = ROOT / admission['mock_evidence'][0]['path']
        bundle = run_result.parents[2]
        bundles[str(bundle)] = bundle
        admissions.append(evidence(admission_path))
    assert dict(primary) == native_summary['primary_native_counts']
    assert totals['tasks'] == native_summary['tasks'] == language['tasks'] == 175
    assert totals['business_cases'] == source_audit['business_cases'] == 158
    assert totals['scenarios'] == 116 and totals['primary_native_main'] == 84320
    mock_totals, mock_projects, mock_items = Counter(), set(), []
    account_sha = sha256((ROOT / 'orchestrator/account_runtime.py').read_bytes()).hexdigest()
    verifier_sha = sha256(check_output(['git', 'show', 'HEAD:orchestrator/project_verifier.py'])).hexdigest()
    for bundle in sorted(bundles.values()):
        result_path = bundle / 'run-001/evidence/result.json'
        cleanup_path = bundle / 'run-001/cleanup.json'
        audit_path = RESEARCH / (bundle.name + '-audit.json')
        browser_path = bundle / 'browser/run-001/diagnostics/result.json'
        result, cleanup, audit, browser = map(read, (result_path, cleanup_path, audit_path, browser_path))
        identity = read(bundle / 'fixtures/catalog-identity.json')
        assert not mock_projects & set(identity['project_keys'])
        mock_projects.update(identity['project_keys'])
        assert result['status'] == result['browser_status'] == cleanup['status'] == audit['status'] == browser['status'] == 'passed'
        assert result['db_cross_checked'] and cleanup['remaining_owned_containers'] == 0
        assert cleanup['runtime_removed'] and cleanup['temporary_token_removed']
        assert result['real_model_calls'] == result['real_oauth_calls'] == 0
        assert browser['business_write_requests'] == 0 and all(row['passed'] for row in browser['checks'])
        source_identity = result['source_identity']
        assert source_identity['runtime_source_verified']
        assert source_identity['actual_account_runtime_sha256'] == account_sha
        assert source_identity['actual_project_verifier_sha256'] == verifier_sha
        summary = audit['summary']
        mock_totals.update(batches=1, paths=summary['selected_paths'], tasks=summary['unique_tasks'],
            code_acceptances=summary['code_acceptances'], modify_targets=summary['unique_modify_targets'],
            unavailable_paths=summary['unavailable_paths'], disclosure_deliveries=summary['disclosure_deliveries'],
            browser_checks=len(browser['checks']), screenshots=len(browser['screenshots']))
        mock_items.append({'bundle': str(bundle.relative_to(ROOT)), 'projects': identity['project_keys'],
            'summary': summary, 'browser_checks': len(browser['checks']),
            'screenshots': len(browser['screenshots']),
            'evidence': [evidence(path) for path in (result_path, cleanup_path, audit_path, browser_path)]})
    assert mock_projects == keys and mock_totals['tasks'] == totals['tasks']
    assert mock_totals['paths'] == 525 and mock_totals['modify_targets'] == 2
    assert mock_totals['code_acceptances'] == 6
    assert {row['project'] for row in delivery['mock_mapping']} == keys
    for row in delivery['mock_mapping']:
        assert row['project_and_environment_bytes_equal']
    focused = read(RESEARCH / 'focused-checks-current.json')
    for name, expected_sha in focused['source_sha256'].items():
        assert evidence(ROOT / name)['sha256'] == expected_sha
    for check in focused['checks']:
        assert check['exit_code'] == 0 and check['status'] == 'passed'
        for field in ('stdout', 'stderr'):
            assert evidence(ROOT / check[field])['sha256'] == check[field + '_sha256']
    structure = read(RESEARCH / 'structure-check-final.json')
    assert structure['status'] == 'passed' and structure['exit_code'] == 0
    for row in structure['logs'].values():
        assert evidence(ROOT / row['path']) == row
    assert read(ROOT / structure['logs']['stdout']['path'])['digest'] == library.digest
    protection = read(RESEARCH / 'workspace-protection-final.json')
    assert protection['status'] == 'passed' and protection['staged_empty'] and protection['cc2api_clean']
    document = {'status': 'available_29_local_verified_source_blocked',
        'scope': '29个可获取固定源码项目的本地正式准入与交付验证；第30仓未满足来源要求，整阶段及母任务均未完成',
        'required_stage_projects': 30, 'verified_stage_projects': 29,
        'unmet_stage_requirements': ['R1', 'R8'], 'full_stage_complete': False,
        'source_blocker': evidence(RESEARCH / 'sqlglot-source-blocker.json'),
        'formal': {'version': library.version, 'digest': library.digest, 'projects': len(library.projects),
            'scenarios': sum(len(project.manifest['scenarios']) for project in library.projects.values()),
            'tasks': sum(len(scene['tasks']) for project in library.projects.values() for scene in project.manifest['scenarios'])},
        'stage_totals': dict(totals), 'task_kinds': dict(kinds), 'primary_native_counts': dict(primary),
        'additional_original_native': [row for item in native_summary['items'] for row in item['additional_original_native']],
        'mock_totals': dict(mock_totals), 'mock_batches': mock_items, 'admissions': admissions,
        'source_evidence_audit': evidence(RESEARCH / 'available-evidence-audit.json'),
        'language_boundary': evidence(RESEARCH / 'available-content-language.json'),
        'focused_checks': evidence(RESEARCH / 'focused-checks-current.json'),
        'structure_check': evidence(RESEARCH / 'structure-check-final.json'),
        'workspace_protection': evidence(RESEARCH / 'workspace-protection-final.json'),
        'delivery': evidence(options.delivery.resolve()), 'delivery_files': delivery['files'],
        'old_files_unchanged': delivery['old_files_unchanged'],
        'git_export_status': 'passed_with_production_source_restoration',
        'raw_checkout_bytes_equal': delivery['git_export']['raw_checkout_bytes_equal'],
        'production_source_restoration': delivery['git_export']['production_source_restoration'],
        'docker_copy_status': delivery['docker_export']['status'],
        'stage_local_commit': 'not_performed_incomplete_stage',
        'primary_head': check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'check_all_status': 'not_run_incomplete_stage', 'real_model_status': 'not_run',
        'real_model_calls': 0, 'real_oauth_calls': 0, 'pushed': False, 'deployed': False,
        'summary_script_sha256': sha256(Path(__file__).read_bytes()).hexdigest()}
    document['pool_direction_gap'] = {'scope': '内容池方向差距，不是逐仓配额或本阶段新增完成条件',
        'scene_direction': [600, 800], 'scene_gap_to_600': max(0, 600 - document['formal']['scenarios']),
        'scene_gap_to_800': max(0, 800 - document['formal']['scenarios']),
        'task_direction': 2000, 'task_gap': max(0, 2000 - document['formal']['tasks'])}
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': document['status'], 'formal': document['formal'],
        'stage_totals': document['stage_totals'], 'mock_totals': document['mock_totals']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
