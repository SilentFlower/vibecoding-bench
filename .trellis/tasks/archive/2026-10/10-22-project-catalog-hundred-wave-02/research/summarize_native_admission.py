"""核逐条原始证据后汇总三十仓原生事实，不把原生汇总当作产品准入。"""
from collections import Counter
import hashlib
import json
from pathlib import Path


ROOT = Path.cwd()
RESEARCH = Path(__file__).resolve().parent
WORK = ROOT / '.deploy/project-catalog-hundred/stage-02'


def main() -> None:
    """核当前镜像完整基线与每条独立期望，主项和附加集合分别统计。@return None。"""
    projects = json.loads((RESEARCH / 'source-index.json').read_text())['projects']
    rows, totals = [], Counter()
    for source in projects:
        key = source['slug']
        admission_path = RESEARCH / (key + '-admission.json')
        admission = json.loads(admission_path.read_text())
        baseline = admission['native_baseline']
        result_path = ROOT / baseline['result']
        if hashlib.sha256(result_path.read_bytes()).hexdigest() != baseline['result_sha256']:
            raise ValueError('完整基线原件摘要变化：' + key)
        actual = json.loads(result_path.read_text())
        if (actual['status'] != 'passed' or not actual['container_removed'] or actual['oom_killed']
                or actual['native']['status'] != 'passed' or admission['source_commit'] != source['revision']):
            raise ValueError('完整基线、清理或固定来源不符：' + key)
        cases = []
        for row in admission['native_evidence']:
            path = ROOT / row['evidence']
            if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
                raise ValueError('业务原件摘要变化：' + key + '/' + row['case'])
            evidence = json.loads(path.read_text())
            if (evidence['expectation_met'] is not True or evidence['expected'] != row['expected']
                    or evidence['result']['status'] != row['expected']):
                raise ValueError('业务路径未满足独立期望：' + key + '/' + row['case'])
            cases.append({'case': row['case'], 'expected': row['expected'], 'evidence': row['evidence'], 'sha256': row['sha256']})
        counts = baseline['counts']
        if sum(counts.values()) != baseline['main_collected']:
            raise ValueError('完整基线主项计数不符：' + key)
        profile = json.loads((WORK / 'drafts/environments' / (key + '-py312') / 'profile/profile.json').read_text())
        rows.append({'project': key, 'source_commit': source['revision'],
            'git_files': admission['source_file_count'], 'scenarios': admission['scenarios'],
            'tasks': admission['unique_tasks'], 'modify_tasks': admission['modify_tasks'],
            'main_executions': baseline['main_collected'], 'main_outcomes': counts,
            'doctest_nodes_in_main': baseline['strict_doctest_nodes'],
            'subtests_separate': baseline['subtest_count'],
            'collection_skips_separate': baseline['collection_skip_count'],
            'baseline_result': baseline['result'], 'baseline_result_sha256': baseline['result_sha256'],
            'baseline_contract_sha256': baseline['contract_sha256'], 'baseline_runner_sha256': baseline['runner_sha256'],
            'declared_resources': {'business': profile['business'], 'regression': profile['regression']},
            'business_and_candidate_cases': cases,
            'additional_fixed_original_suites': admission.get('additional_original_native', [])})
        totals.update(counts)
    output = RESEARCH / 'all-thirty-native-summary.json'
    if output.exists():
        raise ValueError('冻结原生汇总不覆盖')
    result = {'status': 'passed', 'scope': '当前目标镜像的原生事实汇总；产品链、页面、正式交付与模型质量分别统计',
        'projects': len(rows), 'scenarios': sum(row['scenarios'] for row in rows),
        'tasks': sum(row['tasks'] for row in rows), 'modify_tasks': sum(row['modify_tasks'] for row in rows),
        'main_executions': sum(row['main_executions'] for row in rows), 'main_outcomes': dict(totals),
        'verified_independent_cases': sum(len(row['business_and_candidate_cases']) for row in rows),
        'real_model_calls': 0, 'items': rows}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    lines = ['# 三十仓原生证据对账', '',
        '仅汇总当前目标镜像的实际完整原生基线与业务／候选独立期望。产品链、正式准入和模型质量分别验收；真实模型调用0。', '',
        '主执行包含其原生mode与doctest，不把doctest重复加总；subtest与收集阶段skip另列。附加官方入口只归固定原版，不冒充可修改候选累计回归。', '',
        '| 项目 | 场景／任务／修改 | 主执行 | pass／skip／xfail／xpass | doctest（已含） | subtest（另列） | 收集skip（另列） | 业务与候选路径 |',
        '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for row in rows:
        counts = row['main_outcomes']
        lines.append('| ' + row['project'] + ' | ' + '/'.join(str(row[k]) for k in ['scenarios', 'tasks', 'modify_tasks'])
            + ' | ' + str(row['main_executions']) + ' | ' + '/'.join(str(counts[k]) for k in ['passed', 'skipped', 'xfailed', 'xpassed'])
            + ' | ' + str(row['doctest_nodes_in_main']) + ' | ' + str(row['subtests_separate']) + ' | '
            + str(row['collection_skips_separate']) + ' | ' + str(len(row['business_and_candidate_cases'])) + ' |')
    lines += ['', '逐路径原件、SHA、固定提交、脚本和环境资源均见同名JSON；失败尝试仍保留在各仓原始目录。', '']
    (RESEARCH / 'all-thirty-native-summary.md').write_text('\n'.join(lines))
    print(json.dumps({key: value for key, value in result.items() if key != 'items'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
