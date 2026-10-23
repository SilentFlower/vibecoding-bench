"""真实项目场景的冻结内容校验与候选可见投影。"""
from __future__ import annotations

import re
from pathlib import Path

from project_library import canonical_json, read_document, safe_relative, snapshot_tree


CONTENT_SCHEMA = 2
DEVELOPMENT_SCHEMA = 3
TASK_KINDS = frozenset({'understand', 'consult', 'diagnose', 'plan', 'modify'})
CONTENT_ID = re.compile(r'^[A-Za-z][A-Za-z0-9_-]{0,79}$')
CHECKSUM = re.compile(r'^[a-f0-9]{64}$')


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'场景内容缺少有效的 {label}')
    return value


def _identifier(value: object) -> str:
    if not isinstance(value, str) or not CONTENT_ID.fullmatch(value):
        raise ValueError('场景、任务或分支标识不合法')
    return value


def _unique_items(value: object, label: str) -> dict[str, dict]:
    if not isinstance(value, list) or not value:
        raise ValueError(f'{label}必须是非空列表')
    result = {}
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f'{label}定义必须是对象')
        key = _identifier(item.get('id'))
        if key in result:
            raise ValueError(f'{label}标识重复：{key}')
        result[key] = item
    return result


def _file(root: Path, value: object, prefix: str) -> Path:
    relative = safe_relative(value)
    if not relative.startswith(prefix + '/'):
        raise ValueError(f'场景文件必须位于 {prefix} 目录')
    path = root
    for part in relative.split('/'):
        path = path / part
        if path.is_symlink():
            raise ValueError('场景文件路径不能包含链接')
    if not path.is_file():
        raise ValueError(f'场景文件不存在：{relative}')
    return path


def _materials(root: Path, value: object, prefix: str) -> None:
    if (not isinstance(value, list) or any(not isinstance(item, str) for item in value)
            or len(set(value)) != len(value)):
        raise ValueError('素材列表不合法或重复')
    for relative in value:
        _file(root, relative, prefix)


def _setup(root: Path, value: object, prefix: str) -> None:
    if not isinstance(value, list):
        raise ValueError('场景输入物化必须是列表')
    seen = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {'source', 'target'}:
            raise ValueError('物化输入只能声明固定来源和目标')
        _file(root, item['source'], prefix)
        target = safe_relative(item['target'])
        if not target.startswith('app/') or target in seen:
            raise ValueError('业务物化只能写入app目录内的唯一文件')
        seen.add(target)


def validate_scenario_project(root: Path, manifest: object, key: str) -> None:
    """校验稳定身份、素材隔离、依赖和可达分支。

    :param root: 一个冻结项目的内容根目录。
    :param manifest: 已解析的项目定义。
    :param key: 目录声明的项目键。
    :return: None；不完整或矛盾内容抛出 ValueError。
    """
    if (not isinstance(manifest, dict) or type(manifest.get('schema')) is not int
            or manifest['schema'] not in (CONTENT_SCHEMA, DEVELOPMENT_SCHEMA) or manifest.get('project_key') != key):
        raise ValueError('场景项目版本或目录归属不合法')
    for field in ('title', 'category', 'description', 'seed_digest', 'environment'):
        _text(manifest.get(field), field)
    if not CHECKSUM.fullmatch(manifest['seed_digest']):
        raise ValueError('场景初始源码摘要不合法')
    _identifier(manifest['environment'])
    source = manifest.get('source')
    if (not isinstance(source, dict) or not isinstance(source.get('repository'), str)
            or not source['repository'].startswith('https://github.com/')
            or not isinstance(source.get('commit'), str)
            or not re.fullmatch(r'[a-f0-9]{40}', source['commit'])):
        raise ValueError('真实项目必须声明上游仓库和完整固定提交')
    _materials(root, source.get('license_files'), 'seed')
    if not source['license_files']:
        raise ValueError('真实项目必须保留许可证文件')
    scenarios = _unique_items(manifest.get('scenarios'), '场景')
    tasks, owners, edges = {}, {}, {}
    for scenario_id, scenario in scenarios.items():
        for field in ('title', 'goal'):
            _text(scenario.get(field), field)
        scenario_tasks = _unique_items(scenario.get('tasks'), '任务')
        development = manifest['schema'] == DEVELOPMENT_SCHEMA
        if development and len(scenario_tasks) != 1:
            raise ValueError('完整开发场景必须对应一项需求或一个BUG')
        entries = _unique_items(scenario.get('entries'), '场景入口')
        if scenario.get('default_entry') not in entries:
            raise ValueError('场景默认入口不存在')
        for entry in entries.values():
            initial = entry.get('task_ids')
            if (not isinstance(initial, list) or not initial or any(not isinstance(item, str) for item in initial)
                    or len(set(initial)) != len(initial)
                    or any(task_id not in scenario_tasks for task_id in initial)):
                raise ValueError('入口任务不存在或重复')
            _materials(root, entry.get('materials', []), 'disclosure')
            _setup(root, entry.get('setup', []), 'disclosure')
        for task_id, task in scenario_tasks.items():
            if task_id in tasks:
                raise ValueError(f'任务标识在项目内重复：{task_id}')
            tasks[task_id], owners[task_id] = task, scenario_id
            _validate_task(root, task, development=development)
            edges[task_id] = [dependency['task_id'] for dependency in task['requires']]
        reachable = {task_id for entry in entries.values() for task_id in entry['task_ids']}
        for task in scenario_tasks.values():
            for branch in task.get('branches', []):
                for task_id in branch.get('activate_tasks', []):
                    if task_id not in scenario_tasks:
                        raise ValueError('分支只能激活同场景中存在的任务')
        while True:
            expanded = reachable | {task_id for parent in reachable
                for branch in scenario_tasks[parent].get('branches', [])
                for task_id in branch.get('activate_tasks', [])}
            if expanded == reachable:
                break
            reachable = expanded
        if reachable != set(scenario_tasks):
            raise ValueError('场景包含所有入口及分支都无法到达的任务')
        for entry in entries.values():
            possible=set(entry['task_ids'])
            while True:
                expanded=possible|{task_id for parent in possible for branch in scenario_tasks[parent].get('branches',[])
                    for task_id in branch.get('activate_tasks',[])}
                if expanded==possible:
                    break
                possible=expanded
            if any(dependency['task_id'] not in possible for task_id in possible for dependency in scenario_tasks[task_id]['requires']):
                raise ValueError('入口选择的任务缺少可达的必需前置任务')
    visiting, visited = set(), set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise ValueError('场景任务依赖成环')
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in edges[task_id]:
            if dependency not in tasks:
                raise ValueError(f'任务依赖不存在：{dependency}')
            # 首版场景工作区独立；跨场景代码继承必须有显式物化契约才能开放。
            if owners[dependency] != owners[task_id]:
                raise ValueError('首版任务依赖必须位于同一场景')
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in tasks:
        visit(task_id)
    for task in tasks.values():
        for dependency in task['requires']:
            if dependency['artifact'] == 'code' and tasks[dependency['task_id']]['kind'] != 'modify':
                raise ValueError('代码依赖只能引用工程修改任务')


def _validate_task(root: Path, task: dict, *, development: bool = False) -> None:
    if task.get('kind') not in TASK_KINDS:
        raise ValueError('场景任务类型不支持')
    for field in ('goal', 'prompt'):
        _text(task.get(field), field)
    if development:
        if task['kind'] != 'modify' or task.get('development_cycle') not in ('feature', 'bug'):
            raise ValueError('完整开发任务必须声明真实需求或BUG及最终工程交付')
        if 'max_turns' in task:
            raise ValueError('完整开发周期按累计预算控制，不使用旧短题轮数限制')
        _materials(root, task.get('owner_materials', []), 'disclosure')
    else:
        if 'development_cycle' in task or 'owner_materials' in task:
            raise ValueError('完整开发元数据必须使用新内容版本')
        turns = task.get('max_turns', 4)
        if type(turns) is not int or not 1 <= turns <= 8:
            raise ValueError('任务正常回复轮次须为 1～8')
    requires = task.get('requires')
    if not isinstance(requires, list):
        raise ValueError('任务必须显式声明真实依赖')
    seen = set()
    for dependency in requires:
        if (not isinstance(dependency, dict) or dependency.get('artifact') not in ('answer', 'code')
                or dependency.get('task_id') == task['id']):
            raise ValueError('任务依赖类型或归属不合法')
        target = _identifier(dependency.get('task_id'))
        if target in seen:
            raise ValueError('任务依赖重复')
        seen.add(target)
    _materials(root, task.get('materials', []), 'materials')
    _setup(root, task.get('setup', []), 'materials')
    paths = task.get('allowed_paths')
    if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
        raise ValueError('任务必须显式声明允许写入的路径')
    for path in paths:
        safe_relative(path)
    if task['kind'] == 'modify' and not paths:
        raise ValueError('工程修改任务必须声明授权范围')
    outcomes = task.get('outcomes')
    if (not isinstance(outcomes, list) or not outcomes or any(not isinstance(item, str) for item in outcomes)
            or len(set(outcomes)) != len(outcomes)):
        raise ValueError('任务合法结果缺失或重复')
    for outcome in outcomes:
        _identifier(outcome)
    evaluation = task.get('evaluation')
    if not isinstance(evaluation, dict) or type(evaluation.get('version')) is not int or evaluation['version'] < 1:
        raise ValueError('任务必须冻结验收版本')
    rubric = read_document(_file(root, evaluation.get('rubric'), 'verification'))
    if (not isinstance(rubric, dict) or not isinstance(rubric.get('criteria'), list)
            or not rubric['criteria']):
        raise ValueError('任务评审依据缺少判定项')
    _unique_items(rubric['criteria'], '评审判定项')
    for criterion in rubric['criteria']:
        _text(criterion.get('requirement'), '评审判定要求')
        if 'allow_candidate_evidence' in criterion and type(criterion['allow_candidate_evidence']) is not bool:
            raise ValueError('候选交付证据引用许可必须是布尔值')
    if evaluation.get('native') is not None:
        _native_specification(root,evaluation['native'])
    if task['kind'] == 'modify' and not evaluation.get('native'):
        raise ValueError('工程修改必须有独立原生行为验收')
    branches = task.get('branches', [])
    if not isinstance(branches, list):
        raise ValueError('材料分支必须是列表')
    if branches:
        _unique_items(branches, '材料分支')
    for branch in branches:
        _text(branch.get('when'), '材料披露条件')
        _materials(root, branch.get('materials'), 'disclosure')
        _setup(root, branch.get('setup', []), 'disclosure')
        activate = branch.get('activate_tasks', [])
        if (not isinstance(activate, list) or any(not isinstance(item, str) for item in activate)
                or len(set(activate)) != len(activate)):
            raise ValueError('分支激活任务不合法')


def _native_specification(root: Path, relative: str) -> None:
    specification=read_document(_file(root,relative,'verification'))
    if not isinstance(specification,dict) or 'expected' not in specification:
        raise ValueError('原生验收必须声明冻结预期结果')
    _file(root,specification.get('script'),'verification')
    arguments=specification.get('args')
    paths=specification.get('python_paths')
    if (not isinstance(arguments,list) or any(not isinstance(item,str) for item in arguments)
            or not isinstance(paths,list) or not paths or any(not isinstance(item,str) for item in paths)
            or specification.get('resource_profile','business') not in ('business','regression')
            or len(canonical_json(specification))>65536):
        raise ValueError('原生验收参数、路径或资源档案不合法')
    for path in paths:
        safe_relative(path)
    regression=specification.get('regression')
    if regression is not None:
        if not isinstance(regression,dict):
            raise ValueError('原生回归定义必须是对象')
        _file(root,regression.get('runner'),'verification')
        contract=read_document(_file(root,regression.get('contract'),'verification'))
        if (not isinstance(contract,dict) or contract.get('schema')!=1 or not isinstance(contract.get('nodes'),list)
                or not contract['nodes'] or any(not isinstance(node,dict) or set(node)!={'id','kind','outcome'} for node in contract['nodes'])):
            raise ValueError('原生回归缺少冻结节点合同')


def scenario_summary(manifest: dict, *, include_tasks: bool = False) -> dict:
    """生成白名单摘要，隐藏首问以外的分支与评测依据。

    :param manifest: 已校验的 schema 2 项目定义。
    :param include_tasks: 是否附带任务目标；不会公开隐藏材料或 rubric。
    :return: 可用于目录和页面的公开对象。
    """
    result = {field: manifest[field] for field in
        ('project_key', 'title', 'category', 'description', 'seed_digest')}
    result['source'] = {field: manifest['source'][field] for field in ('repository', 'commit', 'license_files')}
    result.update(content_schema=manifest['schema'], scenario_count=len(manifest['scenarios']),
        task_count=sum(len(scenario['tasks']) for scenario in manifest['scenarios']))
    if include_tasks:
        result['scenarios'] = [{'id': scenario['id'], 'title': scenario['title'], 'goal': scenario['goal'],
            'tasks': [{field: task[field] for field in ('id', 'kind', 'goal', 'requires')}
                for task in scenario['tasks']]} for scenario in manifest['scenarios']]
        if manifest['schema'] == DEVELOPMENT_SCHEMA:
            for scenario, public in zip(manifest['scenarios'], result['scenarios']):
                for task, projected in zip(scenario['tasks'], public['tasks']):
                    projected['development_cycle'] = task['development_cycle']
    return result


def scenario_project_digest(root: Path) -> str:
    """分别限制一个项目内容，避免全库共用单源码树上限。

    :param root: 项目根；离线依赖位于库级 environments 中。
    :return: 稳定项目内容摘要。
    """
    return snapshot_tree(root)['digest']


def validate_environment(root: Path, key: str) -> dict:
    """验证冻结 Python 环境档案与逐制品摘要。

    :param root: environments 目录。
    :param key: 项目引用的环境标识。
    :return: 经过校验的环境档案。
    """
    _identifier(key)
    directory = root / key
    if directory.is_symlink():
        raise ValueError('原生环境目录不能是链接')
    profile = read_document(_file(directory, 'profile/profile.json', 'profile'))
    if (not isinstance(profile, dict) or profile.get('id') != key or type(profile.get('schema')) is not int
            or profile['schema'] != 1
            or profile.get('adapter') != 'python-native' or not isinstance(profile.get('python'), str)):
        raise ValueError('原生环境档案不合法')
    for name in ('business', 'regression'):
        resources = profile.get(name)
        if not isinstance(resources, dict):
            raise ValueError('原生环境必须分别声明业务及回归资源')
        for field, lower, upper in (('timeout_sec', 1, 1800), ('memory_mb', 128, 4096), ('pids_limit', 16, 256)):
            value = resources.get(field)
            if type(value) is not int or not lower <= value <= upper:
                raise ValueError('原生环境资源不合法')
    artifacts = profile.get('artifacts')
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError('原生环境缺少离线依赖制品')
    requirements = profile.get('requirements')
    if (requirements is not None and (not isinstance(requirements,list) or not requirements
            or any(not isinstance(item,str) or not re.fullmatch(r'[A-Za-z0-9_.-]+==[A-Za-z0-9_.+!-]+',item) for item in requirements))):
        raise ValueError('原生依赖必须固定精确版本，不能包含选项或动态地址')
    seen, total = set(), 0
    for artifact in artifacts:
        if (not isinstance(artifact, dict) or not isinstance(artifact.get('digest'), str)
                or not CHECKSUM.fullmatch(artifact['digest'])):
            raise ValueError('离线制品摘要不合法')
        relative = safe_relative(artifact.get('path'))
        if relative in seen:
            raise ValueError('离线制品重复')
        seen.add(relative)
        path = _file(directory, relative, 'artifacts')
        total += path.stat().st_size
        if total > 2 * 1024 * 1024 * 1024 or len(seen) > 256:
            raise ValueError('单个原生环境超出制品大小或数量上限')
    return profile
