"""准备明确标注的离线回放，并核真实评审包／严格协议，不评价模型质量。"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / 'orchestrator'))
from project_evaluation import load_rubric, parse_review, review_package, source_evidence
from project_library import ProjectLibrary, digest_json


WORKSPACE = ROOT / '.deploy/project-catalog-hundred/stage-01'


def main() -> None:
    """生成九任务配方并验证正常、披露、无材料和程序失败路径。

    :return: None。
    """
    library = ProjectLibrary(WORKSPACE / 'drafts')
    project = library.projects['cachetools']
    reference = WORKSPACE / 'references/cachetools'
    answers = {
        'CT-U01': 'The returned prices are 35, 35, 35 and 40. Only two real reads occur. The first entry expires at timer=5; membership requires timer < expires, so exactly 5 is a miss. The file update does not notify this TTL cache.',
        'CT-C01': 'This is intentional TTL consistency, not a filesystem watcher or a demonstrated library defect. Explicitly invalidate the cache under application synchronization, shorten the accepted staleness interval, or use an explicit file/version key. Choose atomic publishing and a deliberate consistency policy; neither memoization nor TTL guarantees immediate visibility.',
        'CT-P01': 'Validate a new JSON document before atomically replacing the published file. Use a bounded cache with explicit invalidation or a stable version key and a chosen TTL fallback. Readers must not observe partial writes. A parse error on a miss propagates and is not cached; decide separately whether to retain a known-good version. Avoid exposing mutable cached objects without an ownership/copy policy. This is application design using existing APIs, not a library patch.',
        'CT-D01': 'After the supplied functions and exact calls are disclosed, both methods share the same mapping and default methodkey omits the receiver without adding the method name. The same SKU therefore collides and the second lookup reuses the first price. Separate caches or explicit method namespaces address this reproduction. The initial symptom alone did not prove that cause; no code was changed.',
        'CT-C02': 'Use distinct caches or an explicit namespaced key for each business method, for example a key callback receiving the instance and returning keys.hashkey("retail", sku) versus keys.hashkey("wholesale", sku). Default methodkey ignores the receiver and does not automatically include the method name. Preserve real arguments and distinguish method namespaces from instance ownership. Existing APIs suffice.',
        'CT-U02': 'The default decorator sees three raw call forms: no argument, positional 1, and keyword quantity=1, so it performs three misses even though the function results agree. typedkey adds type distinctions and does not bind defaults or normalize signatures. For this exact signature, key=lambda quantity=1: keys.hashkey(quantity) normalizes the three forms. Type-sensitive keys solve a different problem.',
        'CT-D02': 'The bound and positional class forms supply an instance to the descriptor. _Unbound.__call__ obtains the receiver only from args and rejects empty args before forwarding, even though the original method allows its receiver by keyword. This descriptor boundary explains the TypeError; it is unrelated to TTL or capacity. No files were changed.',
        'CT-M01': 'Implemented receiver binding according to the original wrapped signature for a keyword-capable first parameter, without hardcoding self. Bound/positional calls, instance isolation and info remain intact; positional-only, missing and duplicate receivers remain rejected. Delivered the authorized implementation and meaningful public tests in library/src/cachetools/_descriptor.py and library/tests/test_cachedmethod.py. The original-failing public controls, independent matrix and frozen upstream regression have separate actual validation evidence.',
        'CT-C03': 'The first accounting value is 1 while the mutated list contains two elements. getsizeof is evaluated at insertion/reassignment, not continuously. Explicitly assigning the changed value recalculates the cost to 2. Oversized values still raise ValueError. Prefer immutable owned values or controlled mutation with remeasurement and a bounded application policy; no existing automatic reweigh API is promised.'}
    tasks = {task['id']: task for scene in project.manifest['scenarios'] for task in scene['tasks']}
    recipes = {}
    for key, task in tasks.items():
        recipe = {'task_id': key, 'allowed_paths': task['allowed_paths'],
            'answer': 'MOCK_OUTCOME:' + task['outcomes'][0] + '\n' + answers[key], 'writes': []}
        if task['kind'] == 'modify':
            recipe['writes'] = [{'path': path, 'text': (reference / path).read_text(encoding='utf-8')}
                for path in task['allowed_paths']]
        if key == 'CT-D01':
            recipe['context_requests'] = [{'branch_id': 'price-evidence',
                'answer': 'MOCK_NEED_CONTEXT:price-evidence\nPlease provide the actual relevant functions, shared cache and key configuration, and the exact call order/arguments before I assign a cause.',
                'material_fragments': ['@cachedmethod(lambda obj: obj.cache)', '100 followed by 100']}]
        recipes[key] = recipe
    unavailable = {**recipes['CT-D01'], 'context_requests': [],
        'answer': 'MOCK_OUTCOME:insufficient_information\nThe exact functions, cache/key configuration and call sequence are explicitly unavailable. I cannot determine a root cause. Preserve a minimal reproducer with inputs, cache identities, key callbacks and call order for later analysis; possible key collisions are only a conditional hypothesis. No files were changed.'}
    fixtures = WORKSPACE / 'fixtures/cachetools'
    fixtures.mkdir(parents=True, exist_ok=True)
    (fixtures / 'recipes.json').write_text(json.dumps(recipes, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (fixtures / 'recipe-overrides.json').write_text(json.dumps({'unavailable': {'CT-D01': unavailable}}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    mock_cli = ROOT / '.deploy/project-catalog-second-pack/fixtures/mock_cli.py'
    cases = []
    for key, task in tasks.items():
        recipe = recipes[key]
        rubric = load_rubric(project.root, task)
        sources = source_evidence(project.root, rubric)
        if task['branches'] and any(reference.startswith('disclosure/') for reference in sources):
            raise ValueError('初始rubric提前暴露了隐藏材料')
        variations = [('normal', recipe['answer'], [], 'pass')]
        if key == 'CT-D01':
            branch = task['branches'][0]
            material = '\n'.join((project.root / path).read_text(encoding='utf-8') for path in branch['materials'])
            if not all(fragment in material for fragment in recipe['context_requests'][0]['material_fragments']):
                raise ValueError('披露配方没有匹配真实材料')
            variations = [('disclose', recipe['context_requests'][0]['answer'], [], 'disclose'),
                ('normal', recipe['answer'], [{'role': 'assistant', 'content': recipe['context_requests'][0]['answer']},
                    {'role': 'user', 'content': material}], 'pass'),
                ('unavailable', unavailable['answer'], [{'role': 'user', 'content': (project.root / 'disclosure/unavailable.md').read_text()}], 'pass')]
        if task['kind'] == 'modify':
            variations.append(('program-failed', recipe['answer'], [], 'uncertain'))
        for variation, answer, additions, expected in variations:
            conversation = [{'role': 'user', 'content': task['prompt']}, *additions]
            job = {'job_id': len(cases) + 1, 'task_id': len(cases) + 1, 'turn_no': 1,
                'response_digest': digest_json(answer), 'basis_digest': digest_json(rubric),
                'input_digest': digest_json(conversation), 'resolved_model': 'offline-fixture'}
            candidate = {item['path']: {'text': item['text']} for item in recipe['writes']}
            package = review_package(job, task, rubric, answer, task['prompt'],
                {'status': 'failed' if variation == 'program-failed' else 'passed'}, sources,
                conversation=conversation, candidate_files=candidate)
            if additions:
                package['allowed_branches'] = []
            packet = fixtures / (str(job['job_id']) + '-review-package.json')
            packet.write_text(json.dumps(package, ensure_ascii=False), encoding='utf-8')
            completed = subprocess.run([sys.executable, str(mock_cli), '--verify-review-json', str(packet)],
                capture_output=True, text=True, check=True, timeout=10)
            parsed = parse_review(completed.stdout, package)
            if parsed['decision'] != expected:
                raise ValueError('实际评审协议结果不符合该路径')
            cases.append({'task': key, 'variation': variation, 'decision': parsed['decision'], 'outcome': parsed['outcome']})
    proof = {'status': 'passed', 'unique_tasks': len(tasks), 'protocol_cases': len(cases),
        'cases': cases, 'real_model_calls': 0, 'catalog_digest': library.digest,
        'scope': '真实review_package和parse_review协议预检；native状态为已有独立原生证据后的协议输入，不表示本脚本执行程序、驱动真实任务或评价语义质量'}
    (fixtures / 'review-protocol-proof.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in proof.items() if key != 'cases'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
