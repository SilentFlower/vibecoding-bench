"""汇总第三阶段全三十仓；控制项目重跑只计路径，不重复计项目和任务。"""
from argparse import ArgumentParser
from collections import Counter
import json
from pathlib import Path
from sqlite3 import connect
from subprocess import check_output

from audit_available_evidence import ROOT, RESEARCH, WORK, checksum, read
from summarize_available_verification import evidence
from verify_delivery import ProjectLibrary, files


def main() -> None:
    """全部真实证据、正式目录和最终交付一致才保存全批汇总。@return None。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--delivery', type=Path, required=True)
    parser.add_argument('--final-bundle', type=Path, required=True)
    options = parser.parse_args()
    output = RESEARCH / 'full-verification-summary.json'
    assert not output.exists()
    old = read(RESEARCH / 'available-verification-summary.json')
    source = read(RESEARCH / 'source-index.json')
    keys = {row['slug'] for row in source['projects']}
    full_audit = read(RESEARCH / 'full-evidence-audit.json')
    static = read(RESEARCH / 'full-static-checks.json')
    matrix = read(RESEARCH / 'full-task-matrix-audit.json')
    inventory = read(RESEARCH.parent.parent / '10-22-project-catalog-hundred/research/inventory.json')
    expected = {row['slug']: row for row in inventory['projects']}
    library = ProjectLibrary(ROOT / 'project_library')
    delivery = read(options.delivery)
    assert len(library.projects) == len(expected) == 100 and set(library.projects) == set(expected)
    assert len(keys) == full_audit['verified_projects'] == 30
    assert full_audit['status'] == static['status'] == delivery['status'] == 'passed'
    assert matrix['status'] == 'passed' and matrix['projects'] == 30
    for row in matrix['items']:
        assert evidence(ROOT / row['plan']['path']) == row['plan']
        assert checksum(ROOT / 'project_library/projects' / row['project'] / 'project.json') == row['manifest_sha256']
    assert static['catalog_digest'] == delivery['catalog_digest'] == library.digest
    assert delivery['git_export']['status'] == delivery['docker_export']['status'] == 'passed'
    assert delivery['user_index_unchanged'] and not delivery['cleanup_errors']
    for row in old['admissions']:
        assert evidence(ROOT / row['path']) == row
    for row in full_audit['items']:
        assert evidence(ROOT / row['source_proof']['path']) == row['source_proof']
        assert evidence(ROOT / row['baseline_result']['path']) == row['baseline_result']
    totals, counts, kinds, admissions = Counter(), Counter(), Counter(), []
    bundles = {row['bundle']: ROOT / row['bundle'] for row in old['mock_batches']}
    final_bundle = options.final_bundle.resolve(strict=True)
    assert final_bundle.parent == WORK
    bundles[str(final_bundle.relative_to(ROOT))] = final_bundle
    for key in sorted(keys):
        admission_path = RESEARCH / (key + '-admission.json')
        admission = read(admission_path)
        project = library.projects[key]
        assert admission['formal_registered'] and admission['mock_status'] == 'passed' and not admission['pending']
        assert admission['stage'] == 'formal_registered_local_verified'
        assert project.manifest['source']['commit'] == expected[key]['revision'] == admission['source_commit']
        assert project.manifest['source']['repository'] == expected[key]['repository']
        environment = project.manifest['environment']
        assert files(project.root) == files(WORK / 'drafts/projects' / key)
        assert files(ROOT / 'project_library/environments' / environment) == files(WORK / 'drafts/environments' / environment)
        for row in admission['mock_evidence']:
            assert evidence(ROOT / row['path']) == row
        for row in admission['native_evidence']:
            assert checksum(ROOT / row['evidence']) == row['sha256']
            assert row['expectation_met'] and row['expected'] == row['actual_status']
        baseline = admission['native_baseline']
        assert checksum(ROOT / baseline['result']) == baseline['result_sha256']
        counts.update(baseline['counts'])
        totals.update(projects=1, scenarios=admission['scenarios'], tasks=admission['unique_tasks'],
            modify_tasks=admission['modify_tasks'], business_cases=admission['verified_unique_native_cases'],
            primary_native_main=baseline['main_collected'], subtests_separate=baseline['subtest_count'])
        for scene in project.manifest['scenarios']:
            kinds.update(task['kind'] for task in scene['tasks'])
        admissions.append(evidence(admission_path))
    assert dict(counts) == full_audit['primary_native_counts']
    assert totals['tasks'] == static['language']['tasks'] == 183
    assert totals['business_cases'] == full_audit['business_cases'] == 170
    assert totals['scenarios'] == 121 and totals['primary_native_main'] == 85820
    assert totals['subtests_separate'] == 24183 and totals['modify_tasks'] == 3
    mock_totals, admitted, mock_items = Counter(), set(), []
    account_sha = checksum(ROOT / 'orchestrator/account_runtime.py')
    verifier_sha = checksum(ROOT / 'orchestrator/project_verifier.py')
    for bundle in sorted(bundles.values()):
        paths = (bundle / 'run-001/evidence/result.json', bundle / 'run-001/cleanup.json',
            RESEARCH / (bundle.name + '-audit.json'), bundle / 'browser/run-001/diagnostics/result.json')
        result, cleanup, audit, browser = map(read, paths)
        identity = read(bundle / 'fixtures/catalog-identity.json')
        controls = set(identity.get('control_project_keys', []))
        new = set(identity.get('new_project_keys', identity['project_keys']))
        assert not new & admitted and controls <= admitted and not new & controls
        assert set(identity['project_keys']) == new | controls
        admitted.update(new)
        assert result['status'] == result['browser_status'] == cleanup['status'] == audit['status'] == browser['status'] == 'passed'
        assert result['db_cross_checked'] and cleanup['remaining_owned_containers'] == 0
        assert cleanup['runtime_removed'] and cleanup['temporary_token_removed']
        assert result['real_model_calls'] == result['real_oauth_calls'] == 0
        assert browser['business_write_requests'] == 0 and all(row['passed'] for row in browser['checks'])
        identity_runtime = result['source_identity']
        assert identity_runtime['runtime_source_verified']
        assert identity_runtime['actual_account_runtime_sha256'] == account_sha
        assert identity_runtime['actual_project_verifier_sha256'] == verifier_sha
        summary = audit['summary']
        control_tasks = sum(len(scene['tasks']) for key in controls for scene in library.projects[key].manifest['scenarios'])
        new_tasks = sum(len(scene['tasks']) for key in new for scene in library.projects[key].manifest['scenarios'])
        assert summary['unique_tasks'] == new_tasks + control_tasks
        if controls:
            assert controls == {'arrow'} and new == {'sqlglot'} and summary['selected_paths'] == 42
        mock_totals.update(batches=1, paths=summary['selected_paths'], tasks=new_tasks,
            task_entries_summed_across_batches=summary['unique_tasks'], control_replay_paths=control_tasks * 3,
            code_acceptances=summary['code_acceptances'], modify_targets=summary['unique_modify_targets'],
            unavailable_paths=summary['unavailable_paths'], disclosure_deliveries=summary['disclosure_deliveries'],
            browser_checks=len(browser['checks']), screenshots=len(browser['screenshots']))
        mock_items.append({'bundle': str(bundle.relative_to(ROOT)), 'new_projects': sorted(new),
            'control_projects': sorted(controls), 'summary': summary,
            'browser_checks': len(browser['checks']), 'screenshots': len(browser['screenshots']),
            'evidence': [evidence(path) for path in paths]})
    assert admitted == keys and mock_totals['tasks'] == totals['tasks']
    assert mock_totals['paths'] == 567 and mock_totals['control_replay_paths'] == 18
    assert mock_totals['code_acceptances'] == 9 and mock_totals['modify_targets'] == 3
    sql_database = final_bundle / 'run-001/evidence/private-synthetic.sqlite'
    sql_contract = read(ROOT / 'project_library/projects/sqlglot/verification/native-contract.json')
    sql_regressions = []
    with connect('file:' + str(sql_database) + '?mode=ro', uri=True) as connection:
        rows = connection.execute('SELECT j.id,j.native_result_json FROM project_evaluation_jobs j '
            'JOIN project_scenario_tasks t ON t.id=j.task_id WHERE t.task_key=? AND j.status=?',
            ('SG-M01', 'passed')).fetchall()
    assert len(rows) == 3
    for job_id, raw in rows:
        mechanical = json.loads(raw)
        native = mechanical['native']
        regression = native['regression']['regression']
        assert mechanical['status'] == native['status'] == native['business']['status'] == native['regression']['status'] == 'passed'
        assert regression['status'] == 'passed' and regression['collection_matches_contract'] is True
        assert regression['collected'] == 1500 and regression['subtest_count'] == 21780
        assert regression['subtests_match_contract'] is True and regression['subtest_contract'] == sql_contract['subtests']
        assert regression['counts']['passed'] == 1500 and sum(regression['counts'].values()) == 1500
        sql_regressions.append({'evaluation_job_id': job_id, 'status': 'passed', 'main_collected': 1500,
            'subtests_separate': 21780, 'subtest_contract': regression['subtest_contract']})
    assert {row['project'] for row in delivery['mock_mapping']} == keys
    assert all(row['project_and_environment_bytes_equal'] for row in delivery['mock_mapping'])
    focused = read(RESEARCH / 'focused-checks-sqlglot.json')
    adapter_tests = read(RESEARCH / 'sqlglot-audit-adapter-tests.json')
    assert adapter_tests['status'] == 'passed' and adapter_tests['exit_code'] == 0
    for name, expected_sha in adapter_tests['source_sha256'].items():
        assert checksum(RESEARCH / name) == expected_sha
    for name, expected_sha in focused['source_sha256'].items():
        assert checksum(ROOT / name) == expected_sha
    for check in focused['checks']:
        assert check['exit_code'] == 0 and check['status'] == 'passed'
        for field in ('stdout', 'stderr'):
            assert checksum(ROOT / check[field]) == check[field + '_sha256']
    for row in (static['structure']['stdout'], static['structure']['stderr']):
        assert evidence(ROOT / row['path']) == row
    assert read(ROOT / static['structure']['stdout']['path'])['digest'] == library.digest
    formal = {'version': library.version, 'digest': library.digest, 'projects': len(library.projects),
        'scenarios': sum(len(p.manifest['scenarios']) for p in library.projects.values()),
        'tasks': sum(len(s['tasks']) for p in library.projects.values() for s in p.manifest['scenarios'])}
    document = {'status': 'all_30_local_verified_pending_check_all',
        'scope': '完整三十仓本地正式准入及产品链与交付；正式Check-All、规范同步和本地提交由后续runner动作独立记录',
        'required_stage_projects': 30, 'verified_stage_projects': 30, 'unmet_stage_requirements': [],
        'full_stage_implementation_complete': True, 'formal': formal, 'stage_totals': dict(totals),
        'task_kinds': dict(kinds), 'primary_native_counts': dict(counts),
        'additional_original_native': old['additional_original_native'],
        'mock_totals': dict(mock_totals), 'new_task_mock_paths': mock_totals['paths'] - mock_totals['control_replay_paths'],
        'mock_batches': mock_items, 'admissions': admissions,
        'sqlglot_product_full_regressions': {'scope': '三组入口的重复执行证据，不增加任务或原生基线分母',
            'database': evidence(sql_database), 'items': sql_regressions},
        'source_evidence_audit': evidence(RESEARCH / 'full-evidence-audit.json'),
        'task_matrix': evidence(RESEARCH / 'full-task-matrix-audit.json'),
        'static_checks': evidence(RESEARCH / 'full-static-checks.json'),
        'focused_checks': evidence(RESEARCH / 'focused-checks-sqlglot.json'),
        'audit_adapter_tests': evidence(RESEARCH / 'sqlglot-audit-adapter-tests.json'),
        'mock_audit_recipe': evidence(RESEARCH / 'mock-audit-recipe-provenance.json'),
        'historical_partial_summary': evidence(RESEARCH / 'available-verification-summary.json'),
        'unverified_external_tests': full_audit['unverified_external_tests'],
        'public_scope_approval': full_audit['public_scope_approval'],
        'delivery': evidence(options.delivery.resolve()), 'delivery_files': delivery['files'],
        'old_files_unchanged': delivery['old_files_unchanged'],
        'raw_checkout_bytes_equal': delivery['git_export']['raw_checkout_bytes_equal'],
        'production_source_restoration': delivery['git_export']['production_source_restoration'],
        'git_export_status': delivery['git_export']['status'], 'docker_copy_status': delivery['docker_export']['status'],
        'primary_head': check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'check_all_status': 'pending_runner_action', 'stage_local_commit': 'pending_runner_action',
        'real_model_status': 'not_run', 'real_model_calls': 0, 'real_oauth_calls': 0,
        'pushed': False, 'deployed': False, 'summary_script': evidence(Path(__file__))}
    document['pool_direction_gap'] = {'scope': '内容深化方向，独立于本轮百项目接入目标',
        'scene_direction': [600, 800], 'scene_gap_to_600': max(0, 600 - formal['scenarios']),
        'scene_gap_to_800': max(0, 800 - formal['scenarios']), 'task_direction': 2000,
        'task_gap': max(0, 2000 - formal['tasks'])}
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: document[key] for key in ('status', 'formal', 'stage_totals', 'mock_totals')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
