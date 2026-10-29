"""从真实任务和已验证参考冻结离线配方，并检查真实评审协议。"""
from __future__ import annotations

import json
import subprocess
import sys
from argparse import ArgumentParser
from pathlib import Path


ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / 'orchestrator'))
from project_evaluation import load_rubric, parse_review, review_package, source_evidence
from project_library import ProjectLibrary, digest_json, snapshot_tree


WORKSPACE = ROOT / '.deploy/project-catalog-hundred/stage-02'


def main() -> None:
    """冻结单仓业务配方，协议检查不冒充模型语义成绩。@return None。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--answers', type=Path, required=True)
    options = parser.parse_args()
    library = ProjectLibrary(WORKSPACE / 'drafts')
    project = library.projects[options.project]
    bank = json.loads(options.answers.read_text(encoding='utf-8'))
    fixtures = WORKSPACE / 'fixtures' / options.project
    fixtures.mkdir(parents=True, exist_ok=False)
    tasks = {task['id']: task for scene in project.manifest['scenarios'] for task in scene['tasks']}
    recipes, overrides, cases = {}, {}, []
    for key, task in tasks.items():
        if key not in bank or not bank[key].strip():
            raise ValueError('任务缺少实际业务答案：' + key)
        recipe = {'task_id': key, 'project_key': options.project, 'simulation': True,
            'allowed_paths': task['allowed_paths'], 'writes': [], 'outcome': task['outcomes'][0],
            'answer': bank[key].strip() + '\nMOCK_OUTCOME:' + task['outcomes'][0] + '\n'}
        if task['kind'] == 'modify':
            reference = WORKSPACE / 'references' / options.project
            before, after = snapshot_tree(project.root / 'seed')['files'], snapshot_tree(reference)['files']
            changed = {path for path in before.keys() | after.keys() if before.get(path) != after.get(path)}
            if not changed or changed != set(task['allowed_paths']):
                raise ValueError('参考实际修改与授权文件不一致')
            recipe['writes'] = [{'path': path, 'text': (reference / path).read_text(encoding='utf-8')}
                for path in sorted(changed)]
        rubric = load_rubric(project.root, task)
        sources = source_evidence(project.root, rubric)
        variations = [('normal', recipe['answer'], [], 'pass')]
        if task['branches']:
            if len(task['branches']) != 1:
                raise ValueError('多个披露分支需要独立实际配方，不能猜测')
            branch = task['branches'][0]
            material = '\n'.join((project.root / path).read_text(encoding='utf-8').strip()
                for path in branch['materials'])
            ask = bank[key + '-question'].strip() + '\nMOCK_NEED_CONTEXT:' + branch['id'] + '\n'
            request = {'branch_id': branch['id'], 'answer': ask,
                'material_fragments': [(project.root / path).read_text(encoding='utf-8').strip()
                    for path in branch['materials']]}
            recipe['context_requests'] = [request]
            unavailable = {**recipe, 'outcome': 'insufficient_information',
                'answer': bank[key + '-unavailable'].strip() + '\nMOCK_OUTCOME:insufficient_information\n'}
            unavailable.pop('context_requests')
            overrides.setdefault('unavailable', {})[key] = unavailable
            unavailable_material = (project.root / 'disclosure/unavailable.md').read_text(encoding='utf-8')
            variations = [('disclose', ask, [], 'disclose'),
                ('normal', recipe['answer'], [{'role': 'assistant', 'content': ask},
                    {'role': 'user', 'content': material}], 'pass'),
                ('unavailable', unavailable['answer'], [{'role': 'user', 'content': unavailable_material}], 'pass')]
            if any(path.startswith('disclosure/') for path in sources):
                raise ValueError('初始评审源码证据不能提前包含隐藏材料')
        if task['kind'] == 'modify':
            variations.append(('program-failed', recipe['answer'], [], 'uncertain'))
        recipes[key] = recipe
        for variation, answer, additions, expected in variations:
            conversation = [{'role': 'user', 'content': task['prompt']}, *additions]
            job = {'job_id': len(cases) + 1, 'task_id': len(cases) + 1, 'turn_no': 1,
                'response_digest': digest_json(answer), 'basis_digest': digest_json(rubric),
                'input_digest': digest_json(conversation), 'resolved_model': 'offline-fixture'}
            package = review_package(job, task, rubric, answer, task['prompt'],
                {'status': 'failed' if variation == 'program-failed' else 'passed'}, sources,
                conversation=conversation, candidate_files={item['path']: {'text': item['text']}
                    for item in recipe['writes']})
            if additions:
                package['allowed_branches'] = []
            packet = fixtures / (str(job['job_id']) + '-review-package.json')
            packet.write_text(json.dumps(package, ensure_ascii=False), encoding='utf-8')
            completed = subprocess.run([sys.executable,
                str(ROOT / '.deploy/project-catalog-second-pack/fixtures/mock_cli.py'),
                '--verify-review-json', str(packet)], capture_output=True, text=True, check=True, timeout=10)
            result = parse_review(completed.stdout, package)
            if result['decision'] != expected:
                raise ValueError('严格评审协议结果与当前路径不一致')
            cases.append({'task': key, 'variation': variation, 'decision': result['decision'], 'outcome': result['outcome']})
    for filename, value in [('recipes.json', recipes), ('recipe-overrides.json', overrides),
            ('review-protocol-proof.json', {'status': 'passed', 'unique_tasks': len(tasks),
                'protocol_cases': len(cases), 'cases': cases, 'real_model_calls': 0,
                'catalog_digest': library.digest,
                'scope': '真实评审包与严格协议预检；native状态为协议输入，实际程序、真实产品链及语义质量分别验证'})]:
        (fixtures / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'project': options.project, 'tasks': len(tasks), 'protocol_cases': len(cases),
        'status': 'passed', 'real_model_calls': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
