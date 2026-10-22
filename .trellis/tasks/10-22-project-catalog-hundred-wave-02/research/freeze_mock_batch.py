"""按已就绪项目冻结独立内容快照和实际入口清单，拒绝模拟未制作内容。"""
from __future__ import annotations

import json
import sys
from argparse import ArgumentParser
from collections import Counter
from pathlib import Path
from shutil import copy2, copytree


ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / 'orchestrator'))
from project_library import ProjectLibrary


WORKSPACE = ROOT / '.deploy/project-catalog-hundred/stage-02'


def save(path: Path, value) -> None:
    """保存冻结输入。@param path 目标。@param value JSON值。@return None。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main() -> None:
    """从实际manifest生成三种材料与授权入口的整链模拟。@return None。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--batch', required=True)
    parser.add_argument('--projects', nargs='+', required=True)
    options = parser.parse_args()
    bundle = WORKSPACE / options.batch
    bundle.mkdir(parents=True, exist_ok=False)
    library = ProjectLibrary(WORKSPACE / 'drafts')
    recipes, overrides, manifests = {}, {}, {}
    for key in options.projects:
        project = library.projects[key]
        manifests[key] = project.manifest
        copytree(project.root, bundle / 'library/projects' / key)
        environment = project.manifest['environment']
        copytree(WORKSPACE / 'drafts/environments' / environment, bundle / 'library/environments' / environment)
        directory = WORKSPACE / 'fixtures' / key
        bank = json.loads((directory / 'recipes.json').read_text(encoding='utf-8'))
        for task, recipe in bank.items():
            if task in recipes:
                raise ValueError('任务ID重复，不能冻结')
            recipes[task] = recipe
        for entry, bank in json.loads((directory / 'recipe-overrides.json').read_text(encoding='utf-8')).items():
            overrides.setdefault(entry, {}).update(bank)
    save(bundle / 'library/catalog.json', {'schema': 2,
        'version': 'real-project-scenarios-hundred-' + options.batch, 'projects': options.projects})
    frozen = ProjectLibrary(bundle / 'library')
    stages = []
    for number in (1, 2, 3):
        selected, choices, kinds = [], {}, Counter()
        for key, manifest in manifests.items():
            chosen = {}
            for scene in manifest['scenarios']:
                tasks = {task['id']: task for task in scene['tasks']}
                by_id = {entry['id']: entry for entry in scene['entries']}
                if number == 1:
                    entry = by_id[scene['default_entry']]
                elif number == 2 and 'unavailable' in by_id:
                    entry = by_id['unavailable']
                elif number == 3 and any(task['kind'] == 'modify' for task in tasks.values()):
                    entry = by_id.get('modify_direct', by_id[scene['default_entry']])
                else:
                    alternatives = [entry for entry in scene['entries']
                        if all(tasks[task]['kind'] != 'modify' for task in entry['task_ids'])]
                    entry = (min(alternatives, key=lambda entry: (len(entry['task_ids']), entry['id']))
                        if alternatives else by_id[scene['default_entry']])
                if entry['id'] != scene['default_entry']:
                    chosen[scene['id']] = entry['id']
                selected.extend(entry['task_ids'])
                kinds.update(tasks[task]['kind'] for task in entry['task_ids'])
            choices[key] = chosen
        stages.append({'name': '模拟百项目扩容 ' + options.batch + ' 第' + str(number) + '组入口',
            'project_keys': options.projects, 'count': len(selected), 'scenario_entries': choices,
            'recipe_overrides': {}, 'selected_task_keys': selected,
            'complete_metadata_rows': len(recipes), 'expected_code_acceptances': kinds['modify'],
            'selected_kind_counts': dict(kinds), 'simulation': True})
    if set(task for stage in stages for task in stage['selected_task_keys']) != set(recipes):
        raise ValueError('入口清单未覆盖全部真实任务')
    prompt_project = options.projects[0]
    prompt_task = manifests[prompt_project]['scenarios'][0]['tasks'][0]['id']
    for name, value in [('recipes.json', recipes), ('recipe-overrides.json', overrides),
            ('stages.json', stages), ('catalog-identity.json', {'version': frozen.version,
                'digest': frozen.digest, 'project_keys': options.projects, 'projects': len(frozen.projects),
                'scenarios': sum(len(manifest['scenarios']) for manifest in manifests.values()),
                'tasks': len(recipes), 'prompt_project': prompt_project, 'prompt_task': prompt_task,
                'real_model_calls': 0, 'production_deployed': False})]:
        save(bundle / 'fixtures' / name, value)
    copy2(ROOT / '.deploy/project-catalog-second-pack/fixtures/mock_cli.py', bundle / 'fixtures/mock_cli.py')
    (bundle / 'browser').mkdir()
    print(json.dumps({'bundle': str(bundle), 'projects': options.projects, 'unique_tasks': len(recipes),
        'path_executions': sum(stage['count'] for stage in stages)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
