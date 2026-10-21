"""独立核对原始 XML、节点、业务 JSON、wheel 摘要及清理证据。"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RESEARCH = ROOT.parent.parent
DRAFT = RESEARCH / 'content-drafts/python-frontmatter'
REPOSITORY_ROOT = RESEARCH.parents[3]


def read(path: Path) -> object:
    """读取已落盘证据。@param path 路径。@return JSON 数据。"""
    return json.loads(path.read_text(encoding='utf-8'))


def normalized(name: str) -> str:
    """规范发行包名。@param name 名称。@return 规范名称。"""
    return re.sub(r'[-_.]+', '-', name).lower()


def main() -> None:
    """证据全部满足后更新环境验证状态，不把参考修复称模型成绩。@return None。"""
    evidence = ROOT / 'evidence'
    container = read(evidence / 'container.json')
    config = container['actual_config']
    assert container['exit_code'] == 0
    assert container['image_id'] == 'sha256:d055c5f0035c8fb3f204ed97d6f774a38afdb3515f5503f7fa028adb6a5e908d'
    assert config['user'] == '1000:1000' and config['network_mode'] == 'none' and config['read_only'] is True
    assert config['memory_bytes'] == config['memory_swap_bytes'] == 512 * 1024 * 1024
    assert config['pids_limit'] == 64 and config['cap_drop'] == ['ALL']
    assert read(evidence / 'cleanup.json')['removed'] is True
    coverage = read(DRAFT / 'verification/reference/existing-native-coverage.json')
    expected_nodes = set(coverage['baseline_nodeids'] + coverage['supplement_nodeids'])
    native = {}
    for name in ['baseline', 'reference']:
        tree = ET.parse(evidence / (name + '-tests.xml')).getroot()
        cases = list(tree.iter('testcase'))
        collection = read(evidence / (name + '-collection.json'))
        nodes = {item['nodeid'] for item in collection['collection']}
        doctests = {item['nodeid'] for item in collection['collection'] if item['item_type'] == 'DoctestItem'}
        assert len(cases) == len(nodes) == 67 and nodes == expected_nodes
        assert doctests == set(coverage['supplement_nodeids']) and len(doctests) == 11
        assert not list(tree.iter('failure')) and not list(tree.iter('error')) and not list(tree.iter('skipped'))
        assert collection['exit_code'] == 0
        calls = [item for item in collection['reports'] if item['when'] == 'call']
        assert len(calls) == 67 and all(item['outcome'] == 'passed' for item in calls)
        process = read(evidence / (name + '-native-process.json'))
        assert process['exit_code'] == 0
        native[name] = {'passed': 67, 'failed': 0, 'errors': 0, 'skipped': 0, 'strict_doctest_items': 11,
            'ordinary_items': 56, 'matches_all_existing_native_nodes': True, 'module': collection['module'],
            'elapsed_sec_including_python_startup': process['elapsed_sec'], 'max_rss_kib': process['max_rss_kib']}
    business = {}
    for name, log in [('consult', 'consult-business.log'), ('shallow', 'shallow-business.log')]:
        actual = read(evidence / log)
        expected = read(DRAFT / ('verification/' + name + '.native.json'))['expected']
        assert actual == expected
        business[name] = {'matched_frozen_expected': True, 'actual': actual}
    repair_specification = read(DRAFT / 'verification/repair.native.json')
    original = read(evidence / 'original-repair-target.log')
    repaired = read(evidence / 'reference-repair-target.log')
    assert original != repair_specification['expected']
    assert original['candidate_import'] is True and original['content_field'] == {'error_type': 'TypeError'}
    assert repaired == repair_specification['expected']
    business['repair_calibration'] = {'original_target_satisfied': False, 'expected_original_failure': True,
        'reference_target_satisfied': True, 'reference_case_count': len(repaired) - 1,
        'original_actual': original, 'reference_actual': repaired}
    old_observation = read(evidence / 'original-business.log')
    assert old_observation['source_commit'] == 'd2977d71638cb451bc06f2af3bb48e09e0dbe8c6'
    assert old_observation['scenario']['roundtrip_equal'] is True and len(old_observation['observations']) == 20
    assert old_observation['module'].startswith('/work/base/library/')
    business['original_business'] = {'roundtrip_equal': True, 'observations': 20,
        'module': old_observation['module'], 'exit_code': read(evidence / 'original-business-process.json')['exit_code']}
    profile = read(ROOT / 'profile/profile.json')
    for artifact in profile['artifacts']:
        assert hashlib.sha256((ROOT / artifact['path']).read_bytes()).hexdigest() == artifact['digest']
    installed = read(evidence / 'install-report.json')
    distributions = {normalized(item['metadata']['name']): item['metadata']['version'] for item in installed['install']}
    requested = {normalized(requirement.split('==')[0]): requirement.split('==')[1] for requirement in profile['requirements']}
    assert distributions == requested and len(distributions) == 8
    runtime = read(evidence / 'runtime.json')
    assert runtime['uid'] == runtime['gid'] == 1000 and runtime['python'].startswith('3.12.15 ')
    cgroup = read(evidence / 'cgroup-observation.json')
    assert int(cgroup['memory.max']) == 512 * 1024 * 1024 and int(cgroup['pids.max']) == 64
    summary = {'verification_status': 'verified_target_runtime', 'image': container['image_tag'],
        'image_id': container['image_id'], 'source_commit': profile['source_commit'], 'runtime': runtime,
        'native': native, 'business': business, 'artifacts': {'count': len(profile['artifacts']),
            'total_bytes': sum(item['size'] for item in profile['artifacts']), 'all_sha256_verified': True},
        'container_memory_peak_bytes_including_tmpfs': int(cgroup['memory.peak']),
        'container_pids_peak': int(cgroup['pids.peak']),
        'offline_install': read(evidence / 'offline-install-process.json'),
        'cleanup_confirmed': True, 'model_executed': False,
        'scope': '环境与内容验收校准证据，不是待测模型成绩或生产部署'}
    (evidence / 'completion-audit.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    profile.update(python='3.12.15', verification_status='verified_target_runtime',
        verification_evidence='evidence/completion-audit.json', tested_image_id=container['image_id'],
        notes='既有完整测试环境已在指定镜像、无网络512MiB/PID64下验证；资源为保守运行上限，不是最优值，也不代表模型成绩。')
    (ROOT / 'profile/profile.json').write_text(json.dumps(profile, ensure_ascii=False, indent=2) + '\n')
    sys.path.insert(0, str(REPOSITORY_ROOT / 'orchestrator'))
    from project_scenario_content import validate_environment
    validate_environment(ROOT.parent, profile['id'])
    print(json.dumps({'status': summary['verification_status'], 'baseline_passed': native['baseline']['passed'],
        'reference_passed': native['reference']['passed'], 'strict_doctests_each': 11,
        'original_target_expected_failure': True, 'reference_business_cases': 11,
        'wheel_count': len(profile['artifacts']), 'memory_peak_bytes': int(cgroup['memory.peak']),
        'baseline_max_rss_kib': native['baseline']['max_rss_kib'],
        'reference_max_rss_kib': native['reference']['max_rss_kib'], 'cleanup_confirmed': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
