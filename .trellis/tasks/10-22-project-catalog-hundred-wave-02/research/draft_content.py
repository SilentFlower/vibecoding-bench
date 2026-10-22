"""统一序列化内容合同；场景、问题、材料及业务验收必须由逐仓研究提供。"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / 'orchestrator'))
from project_library import snapshot_tree
from project_scenario_content import validate_environment, validate_scenario_project


WORKSPACE = ROOT / '.deploy/project-catalog-hundred/stage-02'


def build_project(key: str, metadata: dict, definitions: list, scenes: list,
        materials: dict, modifications: dict | None = None, branches: dict | None = None,
        extra_entries: dict | None = None, license_files: list[str] | None = None,
        python_paths: list[str] | None = None) -> None:
    """将明确逐仓定义转换为实际schema2草稿。

    :param key: 已固定来源的项目键。
    :param metadata: 中文标题、分类和说明。
    :param definitions: 独立任务的明确业务定义。
    :param scenes: 场景身份、目标和任务分组。
    :param materials: 本项目实际材料正文。
    :param modifications: 各工程目标的精确允许文件。
    :param branches: 人工材料披露合同。
    :param extra_entries: 各场景额外入口。
    :param license_files: 已核原文的许可路径，允许上游构建生成的许可独立保存在seed/app。
    :param python_paths: 已核嵌套包的seed相对导入根；未指定则沿现有根或src布局。
    :return: None；拒绝覆盖已有manifest。
    """
    modifications, branches, extra_entries = modifications or {}, branches or {}, extra_entries or {}
    project = WORKSPACE / 'drafts/projects' / key
    if (project / 'project.json').exists():
        raise ValueError('已有草稿，拒绝覆盖：' + key)
    sources = json.loads(Path(__file__).with_name('source-index.json').read_text(encoding='utf-8'))
    source = next(item for item in sources['projects'] if item['slug'] == key)

    def write(relative: str, content: str | dict) -> None:
        """保存明确材料。@param relative 项目相对路径。@param content 实际内容。@return None。"""
        path = project / relative
        if path.is_absolute() and not path.is_relative_to(project):
            raise ValueError('材料路径越界')
        if '..' in Path(relative).parts:
            raise ValueError('材料路径包含上级目录')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + '\n'
            if isinstance(content, dict) else content, encoding='utf-8')

    for path, content in materials.items():
        write(path, content)
    tasks = {}
    for identifier, kind, goal, prompt, paths, outcome, requirement, native_fields in definitions:
        if identifier in tasks:
            raise ValueError('重复任务：' + identifier)
        task = {'id': identifier, 'kind': kind, 'goal': goal, 'prompt': prompt, 'requires': [],
            'materials': paths, 'allowed_paths': modifications.get(identifier, []),
            'outcomes': [outcome], 'max_turns': 4,
            'evaluation': {'version': 1, 'rubric': 'verification/' + identifier + '.rubric.json', 'semantic': True},
            'branches': branches.get(identifier, [])}
        criteria = [{'id': 'business', 'requirement': requirement, 'evidence': []},
            {'id': 'scope', 'requirement': 'Use the actual supplied evidence and pinned source, respect authorization, and distinguish observed behavior, existing guarantees and proposals.', 'evidence': []}]
        if kind == 'modify':
            if not task['allowed_paths']:
                raise ValueError('修改任务没有授权文件')
            for criterion in criteria:
                criterion['allow_candidate_evidence'] = True
            criteria.append({'id': 'public-tests', 'requirement': 'Deliver meaningful public regression tests in the authorized file that fail on the pinned original and pass after the repair; cite the actual implementation and tests. Preserve all original tests and controls.', 'evidence': [], 'allow_candidate_evidence': True})
        if task['branches']:
            task['outcomes'].append('insufficient_information')
        if native_fields is not None:
            paths_to_python = ['library/src', 'app'] if (project / 'seed/library/src').is_dir() else ['library', 'app']
            if python_paths is not None:
                if not python_paths or any(Path(path).is_absolute() or '..' in Path(path).parts
                        or not (project / 'seed' / path).is_dir() for path in python_paths):
                    raise ValueError('导入根必须属于真实seed目录')
                paths_to_python = python_paths
            native = {'script': 'verification/native_observe.py', 'args': [identifier],
                'python_paths': paths_to_python, 'expected': {'candidate_import': True,
                    **{field: True for field in native_fields}}, 'resource_profile': 'business'}
            if kind == 'modify':
                native['regression'] = {'runner': 'verification/native_regression.py', 'contract': 'verification/native-contract.json'}
            write('verification/' + identifier + '.native.json', native)
            task['evaluation']['native'] = 'verification/' + identifier + '.native.json'
        write('verification/' + identifier + '.rubric.json', {'schema': 1, 'task_id': identifier,
            'source_commit': source['revision'], 'criteria': criteria,
            'comparison': 'Accept equivalent correct reasoning and implementations; do not match wording or a reference answer.'})
        tasks[identifier] = task
    scenario_rows = [{'id': identifier, 'title': title, 'goal': goal, 'default_entry': 'normal',
        'entries': [{'id': 'normal', 'task_ids': selected}, *extra_entries.get(identifier, [])],
        'tasks': [tasks[identifier] for identifier in selected]} for identifier, title, goal, selected in scenes]
    if sorted(task['id'] for scene in scenario_rows for task in scene['tasks']) != sorted(tasks):
        raise ValueError('场景任务归属缺失或重复')
    shutil.copyfile(Path(__file__).with_name(key + '-native-observe.py'), project / 'verification/native_observe.py')
    license_files = (license_files if license_files is not None else
        [str(path.relative_to(project)) for pattern in ('LICENSE*', 'COPYING*')
            for path in (project / 'seed/library').glob(pattern) if path.is_file()])
    if not license_files:
        raise ValueError('未发现已审核的许可文件')
    for relative in license_files:
        path = Path(relative)
        if (path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != 'seed'
                or (project / path).is_symlink() or not (project / path).is_file()):
            raise ValueError('许可必须是seed内已保存的真实文件')
    document = {'schema': 2, 'project_key': key, **metadata,
        'seed_digest': snapshot_tree(project / 'seed')['digest'], 'environment': key + '-py312',
        'source': {'repository': source['repository'], 'commit': source['revision'], 'license_files': license_files},
        'scenarios': scenario_rows}
    # 制作时立即沿真实准入校验，材料或私有合同不合法不能继续冻结模拟输入。
    validate_scenario_project(project, document, key)
    validate_environment(WORKSPACE / 'drafts/environments', document['environment'])
    write('project.json', document)
    catalog = WORKSPACE / 'drafts/catalog.json'
    document = json.loads(catalog.read_text(encoding='utf-8'))
    if key in document['projects']:
        raise ValueError('目录重复注册')
    document['projects'].append(key)
    catalog.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'project': key, 'scenarios': len(scenario_rows), 'tasks': len(tasks),
        'formal_catalog_modified': False}, ensure_ascii=False))
