"""逐仓复核第三阶段全三十仓的固定来源、离线制品和完整原生证据。"""
from collections import Counter
import gzip
from hashlib import sha256
import json
from pathlib import Path
from subprocess import check_output

from audit_available_evidence import ROOT, RESEARCH, WORK, checksum, read, snapshot_tree, source_entries
from summarize_available_verification import evidence
from project_native_regression import _subtest_contract


def public_sqlglot_entries(item: dict) -> dict:
    """核公开主仓全部对象及唯一获准排除的Gitlink。@param item 固定来源。@return 完整公开对象表。"""
    scope_path = RESEARCH / 'sqlglot-public-source-scope.json'
    scope = read(scope_path)
    excluded = scope['excluded_submodule']
    assert scope['user_approved'] is True and scope['source_commit'] == item['revision']
    assert not scope['private_tests_counted_as_passed'] and not scope['set_skip_integration']
    command = ['git', '-C', item['historical_checkout']]
    assert check_output(command + ['rev-parse', 'HEAD'], text=True).strip() == item['revision']
    assert not check_output(command + ['status', '--porcelain'])
    entries, gitlinks = {}, []
    for raw in check_output(command + ['ls-tree', '-rz', '--full-tree', item['revision']]).split(b'\0'):
        if not raw:
            continue
        metadata, name = raw.split(b'\t', 1)
        mode, kind, blob = metadata.decode().split()
        name = name.decode()
        if mode == '160000':
            assert kind == 'commit' and name == excluded['path'] and blob == excluded['commit']
            gitlinks.append(name)
            continue
        assert kind == 'blob' and mode in ('100644', '100755', '120000')
        content = check_output(command + ['cat-file', 'blob', blob])
        entries[name] = {'git_mode': mode, 'git_blob': blob,
            'size': len(content), 'sha256': sha256(content).hexdigest()}
    assert gitlinks == [excluded['path']] and len(entries) == 361
    for row in scope['upstream_evidence']:
        assert evidence(ROOT / row['path']) == row
    return entries


def audit_project(item: dict) -> dict:
    """核单仓真实对象和各原件，不重跑已通过的昂贵测试。@param item 固定来源。@return 审计结果。"""
    key = item['slug']
    project = WORK / 'drafts/projects' / key
    manifest = read(project / 'project.json')
    admission_path = RESEARCH / (key + '-admission.json')
    admission = read(admission_path)
    proof_path = WORK / 'source-proofs' / (key + '.json')
    proof = read(proof_path)
    actual = public_sqlglot_entries(item) if key == 'sqlglot' else source_entries(
        Path(item['historical_checkout']), item['revision'])
    declared = {row['path']: row for row in proof['files']}
    generated = {row['path']: row for row in proof.get('generated_files', [])}
    assert set(actual) == set(declared) and not set(actual) & set(generated)
    assert len(actual) == proof['complete_tracked_files'] == admission['source_file_count']
    assert proof['revision'] == item['revision'] == admission['source_commit']
    snapshot = snapshot_tree(project / 'seed/library')['files']
    assert set(snapshot) == set(actual) | set(generated)
    for name, row in {**declared, **generated}.items():
        if name in actual:
            assert all(row[field] == actual[name][field] for field in ('git_mode', 'git_blob', 'size', 'sha256'))
        assert snapshot[name] == {'digest': row['sha256'], 'size': row['size']}, (key, name)
        executable = bool((project / 'seed/library' / name).stat().st_mode & 0o111)
        assert executable == (row.get('snapshot_mode', row.get('git_mode')) == '100755')
    for name, expected in proof['license_sha256'].items():
        assert checksum(project / 'seed/library' / name) == expected
    for name in manifest['source']['license_files']:
        assert (project / name).is_file() and not (project / name).is_symlink()
    if generated:
        assert evidence(ROOT / proof['generated_provenance']['path']) == proof['generated_provenance']
    environment = WORK / 'drafts/environments' / manifest['environment']
    profile = read(environment / 'profile/profile.json')
    for artifact in profile['artifacts']:
        path = environment / artifact['path']
        assert path.resolve().is_relative_to(environment.resolve())
        assert checksum(path) == artifact['digest'] and path.stat().st_size == artifact['size']
    baseline = admission['native_baseline']
    result_path = ROOT / baseline['result']
    result = read(result_path)
    assert checksum(result_path) == baseline['result_sha256']
    assert result['status'] == 'passed' and result['container_removed'] and not result['oom_killed']
    assert result['network'] == 'none' and result['root_read_only'] and not result['account_credentials_mounted']
    assert result['image_id'] == 'sha256:943ecef29346447036ec35e2156cc1e4a2f32153e483311531794057a8e18216'
    assert result['control_script_sha256'] == checksum(project / 'verification/native_regression.py') == baseline['runner_sha256']
    assert checksum(project / 'verification/native-contract.json') == baseline['contract_sha256']
    assert result['native']['counts'] == baseline['counts']
    assert not any(baseline['counts'][field] for field in ('failed', 'error', 'unexecuted', 'xpassed'))
    tasks = [task for scene in manifest['scenarios'] for task in scene['tasks']]
    required = {'original-' + task['id'] for task in tasks if 'native' in task['evaluation']}
    modifications = [task for task in tasks if task['kind'] == 'modify']
    cases = {row['case']: row for row in admission['native_evidence']}
    if modifications:
        assert len(modifications) == 1
        required.update({'reference-' + modifications[0]['id'], 'reference-full-regression',
            'public-tests-original', 'public-tests-reference'})
        wrong = {name for name in cases if name.startswith('wrong-')}
        assert len(wrong) == 1
        required.update(wrong)
        seed = snapshot_tree(project / 'seed')['files']
        reference = snapshot_tree(WORK / 'references' / key)['files']
        changed = {name for name in seed.keys() | reference.keys() if seed.get(name) != reference.get(name)}
        assert changed == set(modifications[0]['allowed_paths']) == set(admission['reference_changed_paths'])
    else:
        assert not admission['reference_changed_paths']
    assert set(cases) == required and len(cases) == admission['verified_unique_native_cases']
    for row in cases.values():
        case = read(ROOT / row['evidence'])
        assert checksum(ROOT / row['evidence']) == row['sha256']
        assert case['expectation_met'] and case['expected'] == case['result']['status'] == row['actual_status'] == row['expected']
        if row['expected'] == 'failed':
            assert not any(token in case['result'].get('stderr', '') for token in
                ('ModuleNotFoundError', 'ImportError:', 'PermissionError:', 'No space left'))
    for row in admission['native_attempt_history']:
        assert checksum(ROOT / row['summary']) == row['sha256']
    for row in admission['additional_original_native']:
        assert checksum(ROOT / row['path']) == row['sha256'] and read(ROOT / row['path'])['status'] == 'passed'
    if key == 'sqlglot':
        assert evidence(ROOT / admission['scope_approval']['path']) == admission['scope_approval']
        assert evidence(ROOT / admission['subtest_evidence']['path']) == admission['subtest_evidence']
        subtest = read(ROOT / admission['subtest_evidence']['path'])
        archive = subtest['complete_private_archive']
        assert checksum(ROOT / archive['path']) == archive['sha256']
        raw = gzip.decompress((ROOT / archive['path']).read_bytes())
        rows = json.loads(raw)
        assert len(raw) == archive['expanded_bytes'] and sha256(raw).hexdigest() == archive['observed_order_sha256']
        assert len(rows) == 21780 and all(row['outcome'] == 'passed' for row in rows)
        assert _subtest_contract(rows, 'sqlglot-subtests-v1') == subtest['subtests']
        assert read(project / 'verification/native-contract.json')['subtests'] == subtest['subtests']
        assert result['native']['subtest_contract'] == subtest['subtests']
        assert not (project / 'seed/library/sqlglot-integration-tests').exists()
    return {'project': key, 'source_commit': item['revision'], 'git_files': len(actual),
        'generated_files': len(generated), 'offline_artifacts': len(profile['artifacts']),
        'business_cases': len(cases), 'source_proof': evidence(proof_path),
        'baseline_result': evidence(result_path), 'native_counts': baseline['counts'],
        'main_collected': baseline['main_collected'], 'subtest_count': baseline['subtest_count'],
        'status': 'passed'}


def main() -> None:
    """全部三十仓核实后才写新审计，不覆盖历史29仓报告。@return None。"""
    output = RESEARCH / 'full-evidence-audit.json'
    assert not output.exists()
    items = [audit_project(item) for item in read(RESEARCH / 'source-index.json')['projects']]
    assert len(items) == len({row['project'] for row in items}) == 30
    counts = Counter()
    for item in items:
        counts.update(item['native_counts'])
    document = {'status': 'passed', 'scope': '固定公开源码、许可、离线制品及完整适用原生和业务证据；产品链与最终交付另验',
        'verified_projects': len(items), 'git_files': sum(row['git_files'] for row in items),
        'business_cases': sum(row['business_cases'] for row in items),
        'primary_native_main': sum(row['main_collected'] for row in items),
        'subtests_separate': sum(row['subtest_count'] for row in items), 'primary_native_counts': dict(counts),
        'unverified_external_tests': [read(RESEARCH / 'sqlglot-public-source-scope.json')['excluded_submodule']],
        'public_scope_approval': evidence(RESEARCH / 'sqlglot-public-source-scope.json'),
        'historical_29_audit': evidence(RESEARCH / 'available-evidence-audit.json'),
        'audit_script': evidence(Path(__file__)), 'items': items}
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: value for key, value in document.items() if key != 'items'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
