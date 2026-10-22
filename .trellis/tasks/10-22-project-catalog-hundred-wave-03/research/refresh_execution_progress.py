"""从实际准入和目录重算阶段进度，不改auto-loop权威状态或冻结规划。"""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from subprocess import check_output
import sys


def main() -> None:
    """只保存本阶段可重算的进度与尚缺任务表。@return None。"""
    root, research = Path.cwd(), Path(__file__).resolve().parent
    work = root / '.deploy/project-catalog-hundred/stage-03'
    runner = json.loads(check_output([sys.executable, str(root / '.trellis/scripts/auto_loop.py'),
        'status', '--run-id', 'auto-20261021191233'], text=True, cwd=root))
    source = json.loads((research / 'source-index.json').read_text())
    scope_path = research / 'sqlglot-public-source-scope.json'
    public_scope = json.loads(scope_path.read_text()) if scope_path.is_file() else {}
    catalog = json.loads((root / 'project_library/catalog.json').read_text())
    formal = [json.loads((root / 'project_library/projects' / key / 'project.json').read_text()) for key in catalog['projects']]
    completed, drafts, native_ready = [], [], []
    for item in source['projects']:
        key = item['slug']
        project = work / 'drafts/projects' / key
        if (project / 'verification/native-contract.json').exists():
            native_ready.append(key)
        manifest = project / 'project.json'
        if not manifest.exists():
            continue
        data = json.loads(manifest.read_text())
        admission_path = research / (key + '-admission.json')
        admission = json.loads(admission_path.read_text()) if admission_path.exists() else {}
        tasks = [task for scene in data['scenarios'] for task in scene['tasks']]
        if admission.get('formal_registered') and admission.get('stage') == 'formal_registered_local_verified':
            completed.append(key)
        drafts.append({'project': key, 'scenarios': len(data['scenarios']), 'tasks': len(tasks),
            'native_draft_verified': admission.get('verified_unique_native_cases', 0) > 0,
            'admission_stage': admission.get('stage', 'not_run'), 'formal_registered': admission.get('formal_registered', False)})
        plan = research / (key + '-plan.md')
        if not plan.exists():
            lines = ['# ' + key + '实际任务表', '', '固定来源：' + item['repository'] + '@' + item['revision'] + '。', '',
                '本表由实际逐仓源码核对后的已冻结草稿重算；公开／披露材料、独立私有期望和授权以同名manifest及逐项原件为准，不把测试或分支另计任务。', '',
                '| 任务 | 类型 | 用户目标 | 验收与授权 |', '| --- | --- | --- | --- |']
            for task in tasks:
                scope = '仅允许' + '、'.join(task['allowed_paths']) if task['kind'] == 'modify' else '只读，不接受代码检查点'
                native = task['evaluation'].get('native')
                lines.append('| ' + ' | '.join([task['id'], task['kind'], task['goal'],
                    scope + '；' + (native if native else '实际材料消费与语义评审；材料不足合法收口')]) + ' |')
            lines += ['', '原生完整集合与实际资源见同名准入JSON；产品链／页面／API／数据库／Git／Docker通过后才列为本地正式交付。模型调用0，未推送或部署。', '']
            plan.write_text('\n'.join(lines))
    value = {'purpose': '阶段内实际进度快照；auto-loop状态仍以runner为准',
        'updated_at': datetime.now(timezone.utc).isoformat(), 'run_id': runner['run_id'],
        'runner_status': runner['run_status'],
        'outstanding_action': (runner.get('outstanding_action') or {}).get('action'),
        'stage_required_projects': len(source['projects']),
        'completed_current_stage_projects': len(completed), 'completed_project_keys': completed,
        'remaining_current_stage_projects': len(source['projects']) - len(completed),
        'remaining_without_draft_projects': len(source['projects']) - len(drafts),
        'current_runtime_native_frozen_projects': native_ready,
        'formal_totals': {'projects': len(formal), 'scenarios': sum(len(p['scenarios']) for p in formal),
            'tasks': sum(len(s['tasks']) for p in formal for s in p['scenarios']), 'version': catalog['version']},
        'draft_totals': {'projects': len(drafts), 'scenarios': sum(p['scenarios'] for p in drafts),
            'tasks': sum(p['tasks'] for p in drafts)}, 'draft_projects': drafts,
        'blocked_sources': ([] if public_scope.get('user_approved') is True else
            ['sqlglot:固定私有integration-tests gitlink无法公开获取，见sqlglot-source-blocker.json']),
        'unverified_external_tests': ([{'project': 'sqlglot',
            'submodule': public_scope['excluded_submodule'], 'scope_evidence': str(scope_path.relative_to(root))}]
            if public_scope.get('user_approved') is True else []),
        'real_model_calls': 0, 'pushed': False, 'deployed': False}
    (research / 'execution-progress.json').write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key:value[key] for key in ['completed_current_stage_projects', 'formal_totals', 'draft_totals', 'remaining_without_draft_projects']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
