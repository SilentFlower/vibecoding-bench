"""逐项复核百项目来源、三阶段原件和真实交付，重算当前准入台账。"""

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from subprocess import check_output
import sys


ROOT = Path(__file__).resolve().parents[4]
RESEARCH = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'orchestrator'))
from project_library import IGNORED_DIRECTORIES, ProjectLibrary


def require(condition: bool, message: str) -> None:
    """校验真实原件，不依赖assert。@param condition 条件。@param message 错误。@return None。"""
    if not condition:
        raise ValueError(message)


def checksum(path: Path) -> str:
    """读取普通原件摘要。@param path 文件。@return SHA256。"""
    require(path.is_file() and not path.is_symlink(), '原件不存在或是链接：' + str(path))
    return sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    """读取真实JSON。@param path 文件。@return 文档。"""
    checksum(path)
    return json.loads(path.read_text())


def receipt(path: Path) -> dict:
    """绑定原件字节。@param path 文件。@return 路径与摘要。"""
    return {'path': str(path.relative_to(ROOT)), 'sha256': checksum(path)}


def verified(row: dict) -> dict:
    """按已有收据检查原件。@param row 路径及摘要。@return JSON。"""
    path = ROOT / row.get('path', row.get('evidence', ''))
    require(checksum(path) == row['sha256'], '原件SHA不符：' + str(path))
    return read(path)


def files(root: Path) -> dict:
    """按正式快照规则记录文件及执行位。@param root 根目录。@return 文件表。"""
    result = {}
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if set(relative.parts) & IGNORED_DIRECTORIES:
            continue
        require(not path.is_symlink(), '正式内容出现真实链接')
        if path.is_file():
            result[str(relative)] = {'sha256': checksum(path), 'executable': bool(path.stat().st_mode & 0o111)}
    return result


def main() -> None:
    """核当前正式字节及所有新增准入后写独立当前台账。@return None。"""
    initial = read(RESEARCH / 'inventory-initial.json')
    require(checksum(ROOT / initial['research_source']) == initial['research_source_sha256'], '历史研究快照改变')
    library = ProjectLibrary(ROOT / 'project_library')
    original = {row['slug']: row for row in initial['projects']}
    require(len(original) == 100 and set(original) == set(library.projects), '研究与正式百项目集合不相等')
    require(len({row['repository'] for row in original.values()}) == 100, '研究来源仓库重复')
    for row in original.values():
        for prefix in ['review', 'roadmap']:
            require(checksum(ROOT / row[prefix + '_report']) == row[prefix + '_sha256'], '原研究报告或路线改变')
    baseline_keys = {row['slug'] for row in original.values() if row['planned_stage'] is None}
    staged_keys = [key for stage in initial['stages'] for key in stage['projects']]
    require(len(baseline_keys) == 10 and len(staged_keys) == len(set(staged_keys)) == 90,
        '阶段清单不满足10加90无重复')
    require(set(staged_keys) == set(original) - baseline_keys, '阶段清单遗漏项目')
    baseline = read(ROOT / '.trellis/tasks/10-22-project-catalog-hundred-wave-01/research/formal-baseline.json')
    delivery_path = ROOT / '.trellis/tasks/10-22-project-catalog-hundred-wave-03/research/delivery-thirty-local.json'
    delivery = read(delivery_path)
    actual_files = files(ROOT / 'project_library')
    require(actual_files == delivery['inventory'] and len(actual_files) == delivery['files'] == 32188,
        '当前完整正式文件与已验证Git/Docker交付不同')
    for name, value in baseline['files'].items():
        if name != 'catalog.json':
            require(actual_files.get(name) == value, '初始十项目文件改变：' + name)
    for key in baseline_keys:
        require(checksum(ROOT / original[key]['baseline_manifest']) == original[key]['baseline_manifest_sha256'],
            '初始十仓manifest或稳定ID改变')
    require(delivery['catalog_digest'] == library.digest and delivery['git_export']['status'] ==
        delivery['docker_export']['status'] == 'passed', '最终交付缺失或摘要不同')
    require(delivery['git_export']['raw_checkout_bytes_equal'] is False and
        delivery['git_export']['bytes_and_executable_bits_equal'] is True, '原始CRLF差异口径改变')

    runtime = read(ROOT / '.trellis/.runtime/auto-loop/auto-20261021191233.json')
    stage_results, items, mocks = [], [], {}
    native_counts, stage_kinds = Counter(), Counter()
    unique_tasks, covered_tasks = set(), set()
    for stage in initial['stages']:
        number = stage['number']
        task = ROOT / stage['task']
        research = task / 'research'
        work = ROOT / f'.deploy/project-catalog-hundred/stage-{number:02d}'
        sources = read(research / 'source-index.json')['projects']
        require({s['slug'] for s in sources} == set(stage['projects']), '子任务固定清单与母任务不符')
        item = next(q for q in runtime['queue'] if q['task'] == stage['task'])
        state = read(task / 'task.json')
        require(item['status'] == state['status'] == 'completed' and item['last_check']['result'] == 'ok'
            and item['last_check']['effective_depth'] == 'full', '子任务未完成实际全量检查和本地提交')
        check_output(['git', 'merge-base', '--is-ancestor', item['commit'], 'HEAD'], cwd=ROOT)
        require('commit=' + item['commit'] in state['progress']['notes'], '完成记录与实际commit不符')
        if number == 1:
            audit_path = research / 'stage-source-audit-attempt-001.json'
            source_rows = {r['project']: r for r in read(audit_path)['projects']}
        elif number == 2:
            audit_path = research / 'all-thirty-native-summary.json'
            source_rows = {r['project']: r for r in read(audit_path)['items']}
            formal_rows = {r['project']: r for r in read(research / 'all-thirty-formal-summary.json')['items']}
        else:
            audit_path = research / 'full-evidence-audit.json'
            source_rows = {r['project']: r for r in read(audit_path)['items']}
        require(read(audit_path)['status'] == 'passed', '阶段来源原生汇总未通过')
        if number > 1:
            check = read(research / 'check-all-result.json')
            require(check['status'] == 'strict-pass', '阶段检查不是严格通过')
            for row in check.get('evidence', []):
                verified(row)
        before = len(items)
        totals, kinds = Counter(), Counter()
        for source in sources:
            key = source['slug']
            require(source['revision'] == original[key]['revision'] and
                source['repository'] == original[key]['repository'], '固定研究来源发生替换')
            project = library.projects[key]
            manifest = project.manifest
            tasks = [t for s in manifest['scenarios'] for t in s['tasks']]
            require(manifest['source']['commit'] == source['revision'], '正式源码commit不符')
            task_ids = {(key, t['id']) for t in tasks}
            require(not unique_tasks & task_ids and len(task_ids) == len(tasks), '独立任务标识重复')
            unique_tasks.update(task_ids)
            admission_path = research / (key + '-admission.json')
            admission = read(admission_path)
            require(admission['stage'] == 'formal_registered_local_verified' and
                admission['mock_status'] == 'passed' and not admission.get('pending', []) and
                admission['real_model_calls'] == 0, '新增项目没有真实本地准入')
            proof_path = work / 'source-proofs' / (key + '.json')
            proof = read(proof_path)
            sr = source_rows[key]
            expected_sha = (sr['source_proof_sha256'] if number == 1 else
                formal_rows[key]['source_proof']['sha256'] if number == 2 else sr['source_proof']['sha256'])
            require(checksum(proof_path) == expected_sha, '固定来源原件改变')
            require((proof.get('revision') or proof.get('commit')) == source['revision'], '来源证明commit错误')
            declared = {r['path']: r for r in proof['files']}
            source_files = files(project.root / 'seed/library')
            for name, row in declared.items():
                mode = row.get('snapshot_mode', row['git_mode'])
                require(source_files.get(name) == {'sha256': row['sha256'], 'executable': mode == '100755'},
                    '原始源码字节或执行位不符：' + key + '/' + name)
            # 一些上游版本文件不在Git树中；完整最终文件表和各阶段原件另行绑定它们的来源。
            generated = set(source_files) - set(declared)
            require(set(declared) <= set(source_files), '原始源码缺文件')
            if number == 1:
                require(len(generated) == sr['generated_library_files'], '生成源码范围改变')
            else:
                require(generated == {r['path'] for r in proof.get('generated_files', [])}, '生成源码范围改变')
            for name in manifest['source']['license_files']:
                checksum(project.root / name)
            baseline_row = admission.get('native_baseline')
            if number == 1:
                result_path, result_sha = sr['native_result'], sr['native_result_sha256']
                expected_counts, contract_sha = sr['counts'], sr['contract_sha256']
            else:
                result_path, result_sha = baseline_row['result'], baseline_row['result_sha256']
                expected_counts, contract_sha = baseline_row['counts'], baseline_row['contract_sha256']
                require(checksum(project.root / 'verification/native_regression.py') == baseline_row['runner_sha256'],
                    '冻结原生runner改变')
            require(checksum(ROOT / result_path) == result_sha, '原生结果原件改变')
            native_result = read(ROOT / result_path)
            native = native_result['native']
            require(native_result['status'] == native['status'] == 'passed' and native_result['container_removed']
                and not native_result['oom_killed'] and native_result['network'] == 'none'
                and not native_result['account_credentials_mounted'], '原生基线不是完整隔离成功')
            require(native['counts'] == expected_counts and native['collected'] == sum(expected_counts.values()),
                '原生主项口径不符')
            require(not any(expected_counts[k] for k in ['failed', 'error', 'unexecuted']), '原生失败或遗漏')
            require(expected_counts['xpassed'] == (1 if key == 'sqlparse' else 0), '原版XPASS边界改变')
            require(checksum(project.root / 'verification/native-contract.json') == contract_sha, '冻结原生合同改变')
            native_counts.update(expected_counts)
            cases = admission.get('native_evidence', admission.get('evidence', []))
            require(len({c['case'] for c in cases}) == len(cases), '业务路径重复计数')
            names = {c['case'] for c in cases}
            for case in cases:
                raw = verified(case)
                require(raw['expectation_met'] is True and raw['expected'] == raw['result']['status'] ==
                    case['expected'] and raw['real_model_calls'] == 0, '业务正反例原件不满足独立期望')
            modifies = [t for t in tasks if t['kind'] == 'modify']
            if modifies:
                require(all('original-' + t['id'] in names and 'reference-' + t['id'] in names for t in modifies)
                    and {'reference-full-regression', 'public-tests-original', 'public-tests-reference'} <= names
                    and any(n.startswith('wrong-') for n in names), '修改缺原版/参考/公开/反例/完整回归')
            for row in admission['mock_evidence']:
                verified(row)
            mock_rows = admission['mock_evidence']
            result_row = next(r for r in mock_rows if r['path'].endswith('/evidence/result.json'))
            mocks.setdefault(result_row['path'], {'number': number, 'evidence': mock_rows[:4]})
            counts = Counter(t['kind'] for t in tasks)
            kinds.update(counts)
            totals.update(projects=1, scenarios=len(manifest['scenarios']), tasks=len(tasks), modify_tasks=len(modifies),
                business_cases=len(cases), primary_native_main=native['collected'],
                subtests_separate=native.get('subtest_count', 0), git_files=len(declared))
            items.append({'project': key, 'stage': number, 'source_commit': source['revision'],
                'scenarios': len(manifest['scenarios']), 'tasks': len(tasks), 'kinds': dict(counts),
                'source_files': len(declared), 'generated_files': len(generated), 'license_files': manifest['source']['license_files'],
                'admission': receipt(admission_path), 'source_proof': receipt(proof_path),
                'baseline_result': {'path': result_path, 'sha256': result_sha},
                'primary_native_counts': expected_counts, 'main_collected': native['collected'],
                'subtests_separate': native.get('subtest_count', 0), 'business_cases': len(cases),
                'source_scope': admission.get('source_scope', 'complete_pinned_public_repository'),
                'unverified_external_submodules': admission.get('unverified_external_submodules', [])})
        require(len(items) - before == 30, '阶段不是三十仓')
        stage_kinds.update(kinds)
        stage_results.append({'number': number, 'task': stage['task'], 'totals': dict(totals), 'kinds': dict(kinds),
            'source_native_audit': receipt(audit_path), 'local_commit': item['commit'], 'local_status': 'completed',
            'check': item['last_check'], 'close_result': item['close_result'], 'close_blockers': item['close_blockers']})

    mock_totals, mock_items = Counter(), []
    for path, holder in sorted(mocks.items()):
        docs = [(row, verified(row)) for row in holder['evidence']]
        result = next(doc for row, doc in docs if row['path'] == path)
        cleanup = next(doc for row, doc in docs if row['path'].endswith('/cleanup.json'))
        audit = next(doc for row, doc in docs if 'summary' in doc and 'evidence_inventory_digest' in doc)
        browser_row, browser = next((row, doc) for row, doc in docs if '/browser/' in row['path'])
        require(all(doc['status'] == 'passed' for row, doc in docs), '产品链/审计/页面/清理未通过')
        require(result['db_cross_checked'] and result['native_verification'] == 'real' and
            result['real_model_calls'] == result['real_oauth_calls'] == 0, '模拟错误计为真实模型')
        require(cleanup['remaining_owned_containers'] == 0 and cleanup['runtime_removed'] and
            cleanup['temporary_token_removed'], '产品链隔离资源未清理')
        require(not audit['failures'] and all(c['passed'] for c in browser['checks']), '独立审计或页面失败')
        summary = audit['summary']
        require(summary['maximum_work_intervals'] <= 2 and summary['sampled_maximum_holders'] <= 2,
            '真实工作或采样持有者超过账号限制')
        require(all(t['status'] == 'passed' for t in browser['tasks']), '页面存在未通过路径')
        covered_tasks.update((t['project_key'], t['task_key']) for t in browser['tasks'])
        mock_totals.update(batches=1, paths=summary['selected_paths'], code_acceptances=summary['code_acceptances'],
            unavailable_paths=summary['unavailable_paths'], disclosure_deliveries=summary['disclosure_deliveries'],
            browser_checks=len(browser['checks']), screenshots=len(browser['screenshots']))
        mock_items.append({'stage': holder['number'], 'result': path, 'summary': summary,
            'browser_checks': len(browser['checks']), 'screenshots': len(browser['screenshots']),
            'evidence': holder['evidence']})
    require(len(mocks) == 45 and covered_tasks == unique_tasks and len(unique_tasks) == 619,
        '45批真实产品链没有覆盖全部619独立新增任务')
    all_tasks = [t for p in library.projects.values() for s in p.manifest['scenarios'] for t in s['tasks']]
    formal = {'version': library.version, 'digest': library.digest, 'projects': len(library.projects),
        'scenarios': sum(len(p.manifest['scenarios']) for p in library.projects.values()), 'tasks': len(all_tasks),
        'kinds': dict(Counter(t['kind'] for t in all_tasks))}
    require((formal['projects'], formal['scenarios'], formal['tasks']) == (100, 426, 726), '正式全量计数错误')
    api = read(RESEARCH / 'final-api-verification.json')
    require(api['status'] == 'passed' and api['formal']['digest'] == library.digest and
        api['temporary_data_removed'], '最终百项目API探针未通过或未清理')
    for row in api['evidence']:
        verified(row) if row['path'].endswith('.json') else require(checksum(ROOT / row['path']) == row['sha256'], 'DB原件改变')
    scope_path = ROOT / '.trellis/tasks/10-22-project-catalog-hundred-wave-03/research/sqlglot-public-source-scope.json'
    scope = read(scope_path)
    require(scope['user_approved'] and not scope['private_tests_counted_as_passed'] and
        not scope['set_skip_integration'], 'SQLGlot范围不符合用户确认')
    protection_path = ROOT / '.deploy/project-catalog-hundred/final-integration/retained-baseline.json'
    protection = read(protection_path)
    for name, row in protection['files'].items():
        require(checksum(ROOT / name) == row['sha256'] and (ROOT / name).stat().st_mode & 0o777 == row['mode'],
            '无关保留文件改变：' + name)
    require(check_output(['git', '-C', 'cc2api', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() ==
        protection['cc2api_head'] and not check_output(['git', '-C', 'cc2api', 'status', '--porcelain'], cwd=ROOT),
        'cc2api出现意外变化')
    document = {'status': 'passed', 'scope': '固定百项目全集、90新增逐仓证据及45批实际产品原件；母任务Check-All和本地提交仍由runner后续动作完成',
        'formal': formal, 'initial': {'projects': 10, 'scenarios': 45, 'tasks': 107},
        'new_totals': dict(sum((Counter(s['totals']) for s in stage_results), Counter())),
        'new_task_kinds': dict(stage_kinds), 'primary_native_counts': dict(native_counts),
        'original_non_strict_xpass': {'project': 'sqlparse', 'count': 1},
        'mock_totals': dict(mock_totals), 'unique_new_tasks_mock_covered': len(covered_tasks),
        'existing_arrow_control_replay_paths': 18, 'new_task_mock_paths': mock_totals['paths'] - 18,
        'source_accounting_note': '工作区间和采样持有者均不超2；源记账可能在释放后延迟收口，保留各原件观察值。',
        'original_reports_unchanged': 200, 'old_formal_files_unchanged': len(baseline['files']) - 1,
        'all_formal_files_current_equal_delivery': len(actual_files), 'delivery': receipt(delivery_path),
        'raw_git_checkout_bytes_equal': False, 'production_source_restoration': delivery['git_export']['production_source_restoration'],
        'retained_files_unchanged': len(protection['files']), 'retained_baseline': receipt(protection_path),
        'final_api': receipt(RESEARCH / 'final-api-verification.json'), 'public_sqlglot_scope': receipt(scope_path),
        'unverified_external_tests': [scope['excluded_submodule']], 'stages': stage_results, 'projects': items,
        'mock_batches': mock_items, 'pool_direction_gap': {'scenes_to_600': 600 - formal['scenarios'],
            'scenes_to_800': 800 - formal['scenarios'], 'tasks_to_2000': 2000 - formal['tasks']},
        'script': receipt(Path(__file__)), 'real_model_calls': 0, 'real_oauth_calls': 0,
        'pushed': False, 'production_touched': False}
    output = RESEARCH / 'final-integration-audit.json'
    require(not output.exists(), '最终审计不能覆盖历史原件')
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n')
    current = json.loads(json.dumps(initial))
    current.update(initial_inventory=receipt(RESEARCH / 'inventory-initial.json'), initial_remaining_projects=90,
        remaining_projects=0, current_formal=formal, current_admitted_projects=100, newly_admitted_projects=90,
        current_integration_status='verified_pending_parent_check_and_commit', integration_evidence=receipt(output),
        pool_direction_gap=document['pool_direction_gap'], real_model_status='not_run', production_status='not_deployed')
    by_key = {row['project']: row for row in items}
    for row in current['projects']:
        key = row['slug']
        if key in by_key:
            actual = by_key[key]
            row.update(admission_status='formal_registered_local_verified', admission_evidence=[actual['admission'],
                actual['source_proof'], actual['baseline_result']], source_scope=actual['source_scope'],
                unverified_external_submodules=actual['unverified_external_submodules'],
                current_scenarios=actual['scenarios'], current_tasks=actual['tasks'], native_status='passed',
                product_mock_status='passed', local_commit=stage_results[actual['stage'] - 1]['local_commit'])
        else:
            row.update(admission_status='existing_catalog_preserved', admission_evidence=[receipt(output)],
                compatibility_status='original_bytes_and_stable_ids_preserved')
        row.update(real_model_status='not_run_in_this_run', production_status='not_deployed_in_this_run')
    for stage, actual in zip(current['stages'], stage_results):
        stage.update(status='local_completed', totals=actual['totals'], local_commit=actual['local_commit'],
            close_result=actual['close_result'], close_blockers=actual['close_blockers'])
    (RESEARCH / 'inventory.json').write_text(json.dumps(current, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: document[k] for k in ['status', 'formal', 'new_totals', 'primary_native_counts',
        'mock_totals', 'unique_new_tasks_mock_covered', 'pool_direction_gap']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
