#!/usr/bin/env python3
"""把已存在的真实工程合同归入完整开发周期，逐仓记录未准入原因。"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FEATURES = {'click', 'typer', 'xmltodict'}


def document(path: Path) -> dict:
    """读取已经存在的内容定义。

    :param path: 本地内容文件。
    :return: JSON 对象。
    """
    return json.loads(path.read_text(encoding='utf-8'))


def save(path: Path, value: object) -> None:
    """写入可复核、稳定排版的内容文件。

    :param path: 目标文件。
    :param value: 可 JSON 编码的数据。
    :return: None。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def convert(project: Path, old: dict) -> tuple[dict | None, dict]:
    """只复用真实修改与独立验收，普通问答转为原任务内的调查材料。

    :param project: 固定项目根。
    :param old: 原 schema 2 定义。
    :return: 新定义及逐仓重审结果；缺少交付合同的项目不生成可执行任务。
    """
    slug = old['project_key']
    groups = [(scene, [task for task in scene['tasks'] if task['kind'] == 'modify'])
        for scene in old['scenarios']]
    groups = [(scene, tasks) for scene, tasks in groups if tasks]
    mapping = []
    audit = {'project_key': slug, 'status': 'ready' if groups else 'blocked',
        'source': old['source'], 'legacy_manifest_sha256': hashlib.sha256((project / 'project.json').read_bytes()).hexdigest(),
        'research': [f'research/github-projects/{slug}.md', f'research/github-projects/{slug}-roadmap-20.md'],
        'tasks': [], 'legacy_tasks': mapping}
    if not groups:
        audit['reason'] = '现有内容只有理解、咨询、方案或诊断；尚无可独立验收的真实工程交付合同、原版失败与修复通过证据。研究提案保留待核实，不计完整任务。'
        for scene in old['scenarios']:
            mapping.extend({'task_id': task['id'], 'scene_id': scene['id'], 'goal': task['goal'],
                'disposition': 'retained_background', 'complete_task': None} for task in scene['tasks'])
        return None, audit
    new = {key: copy.deepcopy(value) for key, value in old.items() if key != 'scenarios'}
    new.update(schema=3, title=old['title'].replace('工作场景', '开发任务'), scenarios=[],
        description=f'固定真实源码上的 {len(groups)} 项完整需求／BUG；调查、方案确认、实施与修复在各自原会话连续推进。')
    consumed = set()
    for scene, changes in groups:
        # 原代码依赖在同一过滤器兼容目标中归并，不能假装第二项从未修复的基线独立可做。
        task_id = changes[-1]['id'] + '-DEV'
        task = copy.deepcopy(changes[-1])
        goal = '修复过滤器对 Mapping 输入和显式 None 默认值的兼容行为' if slug == 'jinja' else task['goal']
        materials = list(dict.fromkeys(path for item in scene['tasks'] for path in item.get('materials', [])))
        for entry in scene['entries']:
            materials.extend(path for path in entry.get('materials', []) if path not in materials)
        paths = list(dict.fromkeys(path for change in changes for path in change['allowed_paths']))
        original_requirements = '\n\n'.join(change['prompt'] for change in changes)
        prompt = ('We need to complete a real development change in this pinned project. First inspect the actual '
            'source and supplied business reproduction, explain the relevant call path and edge cases, and raise '
            'any clarification questions. Propose a concrete plan with compatibility and test coverage, and wait '
            'for my confirmation before editing. Continue the implementation and any validation fixes in this '
            'same conversation and workspace. The following describes the eventual delivery scope, not an '
            'instruction to skip investigation or plan agreement:\n\n' + original_requirements)
        setup = [copy.deepcopy(item) for change in changes for item in change.get('setup', [])]
        for entry in scene['entries']:
            if entry['id'] == scene['default_entry']:
                setup = [*copy.deepcopy(entry.get('setup', [])), *setup]
        # 需求方只有实际业务材料和待交付合同，私有 rubric、参考补丁与验收源码不进入外部上下文。
        owner_path = f'disclosure/{task_id}-business.md'
        owner_text = ('# Business scope\n\n' + original_requirements + '\n\n# Investigation topics\n\n'
            + '\n'.join('- ' + item['goal'] for item in scene['tasks'] if item['kind'] != 'modify'))
        for relative in materials:
            owner_text += '\n\n# Supplied business material: ' + relative + '\n\n' + (project / relative).read_text(encoding='utf-8')
        (project / 'disclosure').mkdir(exist_ok=True)
        (project / owner_path).write_text(owner_text + '\n', encoding='utf-8')
        task.update(id=task_id, goal=goal, prompt=prompt, requires=[], materials=[path for path in materials if path.startswith('materials/')],
            owner_materials=[owner_path], allowed_paths=paths, development_cycle='feature' if slug in FEATURES else 'bug', branches=[])
        task.pop('max_turns', None)
        if setup:
            task['setup'] = list({item['target']: item for item in setup}.values())
        rubric = document(project / changes[-1]['evaluation']['rubric'])
        rubric.update(task_id=task_id, version=task['evaluation']['version'] + 1)
        rubric.pop('status', None)
        if len(changes) > 1:
            rubric['criteria'] = [{**criterion, 'id': f'c{index}-{criterion["id"]}'}
                for index, change in enumerate(changes, 1)
                for criterion in document(project / change['evaluation']['rubric'])['criteria']]
        rubric['criteria'].append({'id': 'cycle-public-tests', 'allow_candidate_evidence': True,
            'requirement': 'Deliver meaningful public regression tests within the authorized test paths that fail on the pinned original and pass with the change. Preserve the frozen original tests, test controls, and compatibility behavior; cite actual delivered test files. Controller-owned verification is independent evidence and does not replace delivered public tests.', 'evidence': []})
        rubric_path = f'verification/{task_id}.rubric.json'
        save(project / rubric_path, rubric)
        task['evaluation'].update(rubric=rubric_path, semantic=True, version=rubric['version'])
        new['scenarios'].append({'id': scene['id'] + '-DEV', 'title': goal, 'goal': goal,
            'default_entry': 'development', 'entries': [{'id': 'development', 'task_ids': [task_id]}], 'tasks': [task]})
        audit['tasks'].append({'id': task_id, 'type': task['development_cycle'], 'goal': goal,
            'legacy_changes': [change['id'] for change in changes], 'native': task['evaluation']['native'],
            'validation': 'pending_current_execution'})
        for item in scene['tasks']:
            consumed.add(item['id'])
            mapping.append({'task_id': item['id'], 'scene_id': scene['id'], 'goal': item['goal'],
                'disposition': 'delivery' if item['kind'] == 'modify' else 'internal_investigation', 'complete_task': task_id})
    for scene in old['scenarios']:
        mapping.extend({'task_id': task['id'], 'scene_id': scene['id'], 'goal': task['goal'],
            'disposition': 'retained_background', 'complete_task': None} for task in scene['tasks'] if task['id'] not in consumed)
    return new, audit


def main() -> None:
    """生成完整内容及百项目重审清单，不启动模型、账号或部署。

    :return: None。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT / 'project_library')
    parser.add_argument('--activate', action='store_true', help='在双试点通过后切换当前内容目录')
    parser.add_argument('--validation-report', type=Path, help='与当前内容摘要一致的全部任务原生验收回执')
    args = parser.parse_args()
    original = args.root / 'catalog-v37.json'
    if not original.exists():
        current = document(args.root / 'catalog.json')
        if current['schema'] != 2:
            raise ValueError('必须从保留的真实 schema 2 目录生成')
        original.write_bytes((args.root / 'catalog.json').read_bytes())
    legacy = document(original)
    reviewed, ready = [], []
    for slug in legacy['projects']:
        project = args.root / 'projects' / slug
        new, audit = convert(project, document(project / 'project.json'))
        reviewed.append(audit)
        if new:
            save(project / 'development.json', new)
            ready.append(slug)
    catalog = {'schema': 3, 'version': 'real-development-cycles-v1-en', 'project_manifest': 'development.json',
        'projects': ready, 'admission': [{key: value for key, value in row.items() if key in ('project_key', 'status', 'reason')}
            for row in reviewed]}
    save(args.root / 'catalog-development.json', catalog)
    save(args.root / 'development-audit.json', {'schema': 1, 'legacy_version': legacy['version'],
        'legacy_catalog_sha256': hashlib.sha256(original.read_bytes()).hexdigest(),
        'reviewed_projects': len(reviewed), 'executable_projects': len(ready),
        'complete_tasks': sum(len(row['tasks']) for row in reviewed), 'projects': reviewed})
    if args.activate or args.validation_report:
        if not args.validation_report:
            raise ValueError('激活前必须提供当前全部任务的原生正反验证回执')
        sys.path.insert(0, str(ROOT / 'orchestrator'))
        from project_library import ProjectLibrary
        proof = document(args.validation_report)
        library = ProjectLibrary(args.root, catalog_name='catalog-development.json')
        expected = {(slug, scene['tasks'][0]['id']) for slug, project in library.projects.items() for scene in project.manifest['scenarios']}
        actual = {(row['project_key'], row['task_id']) for row in proof.get('results', []) if row.get('status') == 'passed'}
        if (proof.get('status') != 'passed' or proof.get('catalog_digest') != library.digest
                or expected != actual or len(proof.get('results', [])) != len(expected)):
            raise ValueError('原生回执未完整覆盖当前内容版本，不激活目录')
        for row in reviewed:
            for task in row['tasks']:
                task['validation'] = 'passed_original_reference_and_frozen_regression'
        audit = document(args.root / 'development-audit.json')
        audit.update(projects=reviewed, validated_catalog_digest=library.digest)
        save(args.root / 'development-audit.json', audit)
    if args.activate:
        save(args.root / 'catalog.json', catalog)
    print(json.dumps({'reviewed_projects': len(reviewed), 'executable_projects': len(ready),
        'complete_tasks': sum(len(row['tasks']) for row in reviewed), 'blocked_projects': len(reviewed) - len(ready)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
