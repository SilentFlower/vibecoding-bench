"""只读审计当前阶段各小批内容包的真实模拟产物，不执行模型、原生任务或业务写操作。"""
from __future__ import annotations

from argparse import ArgumentParser
from collections import Counter, defaultdict
from hashlib import sha256
from json import dumps, loads
from math import isclose
from pathlib import Path
from shutil import copyfile
from sqlite3 import Row, connect
from stat import S_ISREG
from typing import Any
import re


TOKEN_FIELDS = ('input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens')


def inventory(root: Path) -> dict:
    """读取完整普通文件全集。@param root 只读证据根。@return 路径、字节数及SHA。"""
    result, pending = {}, [root]
    while pending:
        directory = pending.pop()
        if directory.is_symlink():
            raise ValueError('证据目录含链接：' + str(directory))
        for path in sorted(directory.iterdir()):
            if path.is_symlink():
                raise ValueError('证据含链接：' + str(path))
            if path.is_dir():
                pending.append(path)
            elif S_ISREG(path.stat().st_mode):
                raw = path.read_bytes()
                result[str(path.relative_to(root))] = {'size': len(raw), 'sha256': sha256(raw).hexdigest()}
            else:
                raise ValueError('证据不是普通文件：' + str(path))
    return dict(sorted(result.items()))


def select_evidence(run: Path) -> Path | None:
    """定位已完整封存的证据。@param run 运行根。@return 完整证据根或None。"""
    if (run / 'evidence/result.json').is_file():
        return run / 'evidence'
    if not (run / 'runtime.json').is_file():
        return None
    live = Path(_read(run / 'runtime.json')['root'])
    return live / 'evidence' if (live / 'browser-ready.json').is_file() and (live / 'evidence/result.json').is_file() else None


def snapshot(run: Path, destination: Path) -> dict:
    """独立复制完整证据并重算源/副本全集。@param run 运行根。@param destination 新快照根。

    @return 含逐文件SHA、稳定性及快照位置的收据；不修改原运行。
    """
    source = select_evidence(run)
    if source is None:
        raise ValueError('尚无完整证据，不能创建成功快照')
    before = inventory(source)
    destination.mkdir(parents=True, exist_ok=False)
    target = destination / 'evidence'
    target.mkdir()
    for relative in before:
        output = target / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        copyfile(source / relative, output)
        output.chmod(0o600)
    copyfile(run / 'runtime.json', destination / 'runtime.json')
    after, copied = inventory(source), inventory(target)
    receipt = {'schema': 1, 'source': str(source), 'destination': str(target),
        'source_stable': before == after, 'copy_exact': before == copied,
        'files': copied, 'file_count': len(copied), 'inventory_digest': _digest(copied)}
    (destination / 'copy-receipt.json').write_text(dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    if not receipt['source_stable'] or not receipt['copy_exact']:
        raise ValueError('复制期间源证据变化或副本不一致，保留收据并拒绝宣称成功')
    return receipt


def compare_snapshot(evidence: Path, previous: Path) -> dict:
    """核最终归档与独立快照，允许有实证的浏览器标记和备份头变化。

    @param evidence 当前最终证据。@param previous 完整旧快照根。@return 全集、逐SHA和表一致性。
    """
    receipt = _read(previous / 'copy-receipt.json')
    old_root = previous / 'evidence'
    old, current = inventory(old_root), inventory(evidence)
    modified = [name for name in old.keys() & current.keys() if old[name] != current[name]]
    missing, added = sorted(old.keys() - current.keys()), sorted(current.keys() - old.keys())
    allowed, table_results = [], []
    if 'result.json' in modified:
        before, after = _read(old_root / 'result.json'), _read(evidence / 'result.json')
        old_browser, new_browser = before.pop('browser_status', None), after.pop('browser_status', None)
        if before == after and old_browser in (None, 'pending') and new_browser == 'passed':
            allowed.append('result.json')
    if 'private-synthetic.sqlite' in modified:
        paths = [old_root / 'private-synthetic.sqlite', evidence / 'private-synthetic.sqlite']
        with connect(paths[0].as_uri() + '?mode=ro&immutable=1', uri=True) as before, connect(
                paths[1].as_uri() + '?mode=ro&immutable=1', uri=True) as after:
            before.execute('PRAGMA query_only=ON')
            after.execute('PRAGMA query_only=ON')
            schemas = [connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
                for connection in (before, after)]
            names = [row[1] for row in schemas[0] if row[0] == 'table']
            equal = schemas[0] == schemas[1]
            for name in names:
                quoted = '"' + name.replace('"', '""') + '"'
                left, right = before.execute('SELECT * FROM ' + quoted).fetchall(), after.execute('SELECT * FROM ' + quoted).fetchall()
                same = sorted(map(repr, left)) == sorted(map(repr, right))
                equal = equal and same
                table_results.append({'table': name, 'rows': len(left), 'equal': same})
            if equal:
                allowed.append('private-synthetic.sqlite')
    unexpected = sorted(set(modified) - set(allowed))
    valid = receipt['source_stable'] is True and receipt['copy_exact'] is True and old == receipt['files']
    valid = valid and not missing and not added and not unexpected
    return {'status': 'passed' if valid else 'failed', 'snapshot': str(previous),
        'snapshot_receipt_still_exact': old == receipt['files'], 'snapshot_file_count': len(old),
        'archive_file_count': len(current), 'modified': sorted(modified), 'allowed_observed_changes': sorted(allowed),
        'unexpected_changes': unexpected, 'missing': missing, 'added': added,
        'database_tables': table_results, 'archive_inventory_digest': _digest(current)}


def source_files(project_root: Path, rubric: dict) -> dict:
    """独立重建公开源码证据窗口。@param project_root 固定内容。@param rubric 规则。@return 引用文本。"""
    references = {reference for criterion in rubric['criteria'] for reference in criterion['evidence']}
    result = {}
    for reference in references:
        match = re.fullmatch(r'(.+?):(\d+)(?:-(\d+))?', reference)
        relative = match.group(1) if match else reference
        path = Path(relative)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('固定证据引用越界')
        root = project_root if relative.startswith(('materials/', 'disclosure/', 'verification/')) or relative == 'project.json' else project_root / 'seed'
        lines = (root / path).read_text().splitlines()
        line = int(match.group(2)) if match else 1
        end = int(match.group(3)) if match and match.group(3) else line
        lower, upper = (max(0, line - 21), min(len(lines), end + 35)) if match else (0, len(lines))
        result[reference] = '\n'.join(f'{index + 1}: {lines[index]}' for index in range(lower, upper))
    return result


def _read(path: Path) -> Any:
    """读取已存在的普通 JSON 文件；不创建目录或修改输入。"""
    if path.is_symlink():
        raise ValueError('拒绝符号链接输入：' + str(path))
    return loads(path.read_text(encoding='utf-8'))


def _digest(value: Any) -> str:
    """按已经核对的内容协议计算规范 JSON 摘要。"""
    return sha256(dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _parse(value: str | None) -> Any:
    """保留数据库空值，不把缺失事实填成成功或零。"""
    return loads(value) if value is not None else None


def _same_budget(expected: dict, actual: dict) -> bool:
    """仅容忍浮点求和次序造成的微秒误差，不放宽额度及未知状态。"""
    if set(expected) != set(actual):
        return False
    return all(isclose(value, actual[key], rel_tol=0, abs_tol=0.000001) if type(value) in (int, float)
        and type(actual[key]) in (int, float) else type(value) is type(actual[key]) and value == actual[key]
        for key, value in expected.items())


def _native_observation(evidence: Path, source: dict, execution: dict) -> dict:
    """独立读取该来源的精确字节区间，保留计量字段未知值。"""
    start, end = _parse(source['evidence_start_json']), _parse(source['evidence_end_json'])
    name = execution['session_id'] + '.jsonl'
    if not isinstance(start, dict) or not isinstance(end, dict):
        return {'responses': {}, 'complete': False, 'records': [], 'reason': 'missing-boundary'}
    lower, upper = start.get(name, 0), end.get(name, 0)
    path = evidence / 'native-sessions' / str(source['id']) / name
    if (type(lower) is not int or type(upper) is not int or not 0 <= lower <= upper
            or path.is_symlink() or not path.is_file() or path.stat().st_size < upper):
        return {'responses': {}, 'complete': False, 'records': [], 'reason': 'invalid-boundary'}
    data = path.read_bytes()[lower:upper]
    if data and not data.endswith(b'\n'):
        return {'responses': {}, 'complete': False, 'records': [], 'reason': 'partial-line'}
    records, responses = [], {}
    for line in data.splitlines():
        record = loads(line)
        records.append(record)
        message = record.get('message')
        if (record.get('type') != 'assistant' or record.get('isSidechain') or record.get('isMeta')
                or record.get('isApiErrorMessage') or not isinstance(message, dict)
                or message.get('role') != 'assistant' or message.get('model') == '<synthetic>'):
            continue
        identity = message.get('id') or record.get('requestId')
        if not isinstance(identity, str) or not identity:
            return {'responses': {}, 'complete': False, 'records': records, 'reason': 'missing-response-id'}
        usage = message.get('usage')
        values = {field: usage.get(field) if isinstance(usage, dict) and type(usage.get(field)) is int
            and usage[field] >= 0 else None for field in TOKEN_FIELDS}
        key = execution['session_id'] + ':' + identity
        if key in responses:
            values = {field: max(value for value in (responses[key][field], values[field]) if value is not None)
                if responses[key][field] is not None or values[field] is not None else None for field in TOKEN_FIELDS}
        responses[key] = values
    return {'responses': responses, 'complete': bool(responses) or upper == lower, 'records': records}


def _aggregate(observations: list[dict]) -> dict:
    """对来源观察独立去重；全未知小计为 null。"""
    responses = {}
    for observation in observations:
        for key, current in observation['responses'].items():
            previous = responses.get(key)
            responses[key] = current if previous is None else {field: max(value for value in
                (previous[field], current[field]) if value is not None) if previous[field] is not None
                or current[field] is not None else None for field in TOKEN_FIELDS}
    known = {field: [value[field] for value in responses.values() if value[field] is not None] for field in TOKEN_FIELDS}
    return {**{field: sum(values) if values else None for field, values in known.items()},
        'requests': len(responses) if responses else None, 'sources': len(observations),
        'known_sources': sum(item['complete'] for item in observations),
        'known_fields': {field: len(values) for field, values in known.items()},
        'complete': bool(observations) and all(item['complete'] for item in observations)
            and bool(responses) and all(len(values) == len(responses) for values in known.values())}


def _response_text(evidence: Path, source: dict, execution: dict, key: str) -> str:
    """按冻结字节位置核回答所属来源，不以相同 task_key 猜测。"""
    name = execution['session_id'] + '.jsonl'
    if not key.startswith(name + ':'):
        raise ValueError('回答位置不属于固定 session')
    position = int(key[len(name) + 1:])
    start, end = _parse(source['evidence_start_json']), _parse(source['evidence_end_json'])
    if not isinstance(start, dict) or not isinstance(end, dict) or not start.get(name, 0) <= position < end.get(name, 0):
        raise ValueError('回答位置不属于冻结来源字节区间')
    path = evidence / 'native-sessions' / str(source['id']) / name
    with path.open('rb') as stream:
        stream.seek(position)
        raw = stream.readline()
        if stream.tell() > end.get(name, 0) or not raw.endswith(b'\n'):
            raise ValueError('回答越过来源终点或缺少完整行')
    record = loads(raw)
    message = record.get('message', {})
    if record.get('type') != 'assistant' or message.get('role') != 'assistant' or message.get('model') != 'offline-fixture':
        raise ValueError('冻结位置不属于模型替身主回答')
    content = message.get('content')
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return '\n'.join(item['text'] for item in content if isinstance(item, dict) and item.get('type') == 'text' and isinstance(item.get('text'), str))
    raise ValueError('冻结回答缺少可读正文')


def _input_text(evidence: Path, source: dict, execution: dict, key: str) -> str:
    """核实际用户输入的精确来源字节。@param evidence 证据根。@param source 来源。

    @param execution 执行。@param key 固定输入位置。@return 真实输入正文。
    """
    name = execution['session_id'] + '.jsonl'
    if not isinstance(key, str) or not key.startswith(name + ':'):
        raise ValueError('输入不属于固定session')
    position = int(key[len(name) + 1:])
    lower, upper = _parse(source['evidence_start_json']), _parse(source['evidence_end_json'])
    if not lower.get(name, 0) <= position < upper.get(name, 0):
        raise ValueError('实际输入位置超出来源边界')
    path = evidence / 'native-sessions' / str(source['id']) / name
    with path.open('rb') as stream:
        stream.seek(position)
        raw = stream.readline()
        if stream.tell() > upper[name] or not raw.endswith(b'\n'):
            raise ValueError('实际输入字节不完整')
    record = loads(raw)
    if record.get('type') != 'user' or record.get('message', {}).get('role') != 'user':
        raise ValueError('冻结输入不是用户投递')
    return record['message']['content']


def audit(run: Path, catalog: Path, stages_path: Path) -> dict:
    """核对完成快照的运行事实、真实父链、分支消费和计量。

    :param run: 本轮运行或独立快照目录。
    :param catalog: 只读正式内容库目录。
    :param stages_path: 本次实际回放阶段配置。
    :return: 可审查审计报告；尚无完整快照时明确返回 pending。
    """
    evidence = select_evidence(run)
    if evidence is None:
        return {'status': 'pending', 'run': str(run), 'reason': '尚无 browser-ready 的完整 live 证据或最终归档',
            'real_model_quality_assessed': False}
    runtime = _read(run / 'runtime.json')
    inventory_before = inventory(evidence)
    result = _read(evidence / 'result.json')
    checks, failures = [], []

    def check(name: str, condition: bool, **observed: Any) -> None:
        """保留实际失败及证据，不改写被审计结果。"""
        row = {'check': name, 'status': 'passed' if condition else 'failed', **observed}
        checks.append(row)
        if not condition:
            failures.append(row)

    check('完整运行结果', result['status'] == 'passed', actual=result['status'], error=result.get('error'))
    fixture_identity = _read(stages_path.parent / 'catalog-identity.json')
    fixture_sha256 = {name: sha256((stages_path.parent / name).read_bytes()).hexdigest()
        for name in ('catalog-identity.json', 'recipes.json', 'recipe-overrides.json', 'stages.json', 'mock_cli.py')}
    check('实际运行目录与内容身份', result['catalog_version'] == fixture_identity['version']
        and result['catalog_digest'] == fixture_identity['digest']
        and runtime['source_identity']['catalog_override'] == fixture_identity,
        digest=result['catalog_digest'], fixture_files=len(fixture_sha256))
    facts = _read(evidence / 'database-facts.json')
    details = _read(evidence / 'details.json')
    attempts = _read(evidence / 'attempts.json')
    artifacts = _read(evidence / 'artifacts.json')
    usage = _read(evidence / 'usage.json')
    by_table = {name: {row['id']: row for row in rows} for name, rows in facts.items()}
    tasks = by_table['project_scenario_tasks']
    scenes = by_table['project_scenario_instances']
    instances = by_table['project_instances']
    batches = by_table['project_iteration_batches']
    jobs = by_table['project_evaluation_jobs']
    executions = by_table['project_task_executions']
    sources = by_table['project_execution_sources']
    selected = [row for row in tasks.values() if row['selected']]
    public = {task['id']: task for detail in details for scene in detail['scenarios'] for task in scene['tasks']}
    expected_tasks, expected_branches, native_contracts, project_manifests = set(), set(), {}, {}
    for project in fixture_identity['project_keys']:
        manifest = _read(catalog / 'projects' / project / 'project.json')
        project_manifests[project] = manifest
        for scene in manifest['scenarios']:
            for task in scene['tasks']:
                expected_tasks.add(task['id'])
                expected_branches.update((task['id'], branch['id']) for branch in task.get('branches', []))
                if task['kind'] == 'modify':
                    specification = _read(catalog / 'projects' / project / task['evaluation']['native'])
                    native_contracts[task['id']] = _read(catalog / 'projects' / project / specification['regression']['contract'])
    check('本批正式去重内容规模', len(project_manifests) == fixture_identity['projects']
        and sum(len(item['scenarios']) for item in project_manifests.values()) == fixture_identity['scenarios']
        and len(expected_tasks) == fixture_identity['tasks']
        and len(native_contracts) == sum(task['kind'] == 'modify' for manifest in project_manifests.values() for scene in manifest['scenarios'] for task in scene['tasks']))
    requirements = {task['id']: task['requires'] for project in project_manifests.values()
        for scene in project['scenarios'] for task in scene['tasks'] if task['requires']}
    check('本批任务可独立进入', not requirements,
        actual=requirements)
    for instance in instances.values():
        manifest = project_manifests[instance['project_key']]
        check('实例冻结内容身份_' + str(instance['id']), _parse(instance['manifest_json']) == manifest
            and instance['seed_digest'] == manifest['seed_digest'])
    for scene in scenes.values():
        project = instances[scene['instance_id']]['project_key']
        definition = next(item for item in project_manifests[project]['scenarios'] if item['id'] == scene['scenario_key'])
        check('场景冻结内容身份_' + str(scene['id']), _parse(scene['definition_json']) == definition)
    for task in tasks.values():
        scene = scenes[task['scenario_instance_id']]
        definition = next(item for item in _parse(scene['definition_json'])['tasks'] if item['id'] == task['task_key'])
        check('任务冻结内容身份_' + str(task['id']), _parse(task['definition_json']) == definition)
    stage_definitions = _read(stages_path)
    recipes = _read(stages_path.parent / 'recipes.json')
    overrides = _read(stages_path.parent / 'recipe-overrides.json')
    expected_stage_counts, expected_paths, expected_stored_rows, expected_context = [], set(), 0, {}
    check('阶段配置与完成记录数量一致', len(result['stages']) == len(stage_definitions),
        definitions=len(stage_definitions), actual=len(result['stages']))
    for index, stage_definition in enumerate(stage_definitions):
        selected_definitions = []
        for project in stage_definition['project_keys']:
            for scene in project_manifests[project]['scenarios']:
                entry_key = stage_definition.get('scenario_entries', {}).get(project, {}).get(scene['id'], scene['default_entry'])
                entry = next(item for item in scene['entries'] if item['id'] == entry_key)
                expected_stored_rows += len(scene['tasks'])
                selected_definitions.extend((project, scene['id'], entry_key, task_key) for task_key in entry['task_ids'])
        expected_stage_counts.append(len(selected_definitions))
        check('阶段配置数量独立推导_' + str(index + 1), len(selected_definitions) == stage_definition['count'],
            declared=stage_definition['count'], derived=len(selected_definitions))
        if index < len(result['stages']):
            batch_id = result['stages'][index]['batch_id']
            expected_paths.update((batch_id, *item) for item in selected_definitions)
            for project, scene_key, entry_key, task_key in selected_definitions:
                recipe = overrides.get(scene_key + ':' + entry_key, overrides.get(entry_key, {})).get(task_key, recipes[task_key])
                recipe = stage_definition.get('recipe_overrides', {}).get(task_key, recipe)
                requests = recipe.get('context_requests', []) or ([recipe['request_context']] if recipe.get('request_context') else [])
                expected_context[(batch_id, project, scene_key, entry_key, task_key)] = requests
    actual_paths = {(instances[scenes[task['scenario_instance_id']]['instance_id']]['batch_id'],
        instances[scenes[task['scenario_instance_id']]['instance_id']]['project_key'],
        scenes[task['scenario_instance_id']]['scenario_key'], scenes[task['scenario_instance_id']]['entry_key'], task['task_key']) for task in selected}
    check('实际选择路径精确匹配阶段入口', actual_paths == expected_paths, expected=len(expected_paths), actual=len(actual_paths))
    stage_counts = []
    for stage in result['stages']:
        rows = [task for task in selected if instances[scenes[task['scenario_instance_id']]['instance_id']]['batch_id'] == stage['batch_id']]
        stage_counts.append(len(rows))
        check('阶段状态_' + str(stage['stage']), len(rows) == stage['selected_tasks'] and all(task['status'] == 'passed' for task in rows)
            and batches[stage['batch_id']]['status'] == 'completed', selected=len(rows), claimed=stage['selected_tasks'])
    check('全部阶段和唯一任务', stage_counts == expected_stage_counts and len(selected) == sum(expected_stage_counts)
        and len(tasks) == expected_stored_rows and {task['task_key'] for task in selected} == expected_tasks and len(expected_tasks) == fixture_identity['tasks'],
        stage_counts=stage_counts, selected_paths=len(selected), unique_tasks=len({task['task_key'] for task in selected}),
        stored_rows=len(tasks), unselected_rows=sum(not task['selected'] for task in tasks.values()))
    check('选中任务终态', all(task['status'] == 'passed' for task in selected), status_counts=dict(Counter(task['status'] for task in selected)))
    check('公开详情与数据库任务全集一致', set(public) == set(tasks), public_rows=len(public), database_rows=len(tasks))
    for task in selected:
        check('任务结果投影_' + str(task['id']), public[task['id']]['result'] == _parse(task['result_json'])
            and all(public[task['id']][field] == task[field] for field in ('task_key', 'kind', 'selected', 'status', 'phase',
                'turn_no', 'attempt_count', 'infra_recoveries', 'accepted_checkpoint_digest'))
            and public[task['id']]['requires'] == _parse(task['definition_json'])['requires'])
    unavailable = [task for task in selected if scenes[task['scenario_instance_id']]['entry_key'] == 'unavailable']
    expected_unavailable = {task for manifest in project_manifests.values() for scene in manifest['scenarios'] for entry in scene['entries'] if entry['id'] == 'unavailable' for task in entry['task_ids']}
    check('材料不可提供的真实业务结果', {task['task_key'] for task in unavailable} == expected_unavailable
        and all(_parse(task['result_json'])['outcome'] == 'insufficient_information' for task in unavailable),
        actual=[{'task_id': task['id'], 'task_key': task['task_key'], 'result': _parse(task['result_json'])} for task in unavailable])

    # deliveries 未包含在通用事实导出中，只打开已封存备份的只读连接补齐消费事实。
    database = evidence / 'private-synthetic.sqlite'
    with connect(database.as_uri() + '?mode=ro&immutable=1', uri=True) as connection:
        connection.execute('PRAGMA query_only=ON')
        connection.row_factory = Row
        deliveries = [dict(row) for row in connection.execute('SELECT * FROM project_task_deliveries ORDER BY id')]
        for table in ('project_iteration_batches', 'project_instances', 'project_scenario_instances', 'project_scenario_tasks',
                'project_task_attempts', 'project_task_executions', 'project_execution_sources', 'project_work_segments',
                'project_task_deliveries', 'project_evaluation_jobs', 'runs'):
            actual_rows = [dict(row) for row in connection.execute('SELECT * FROM ' + table + ' ORDER BY id')]
            check('保存SQLite与JSON事实_' + table, actual_rows == facts[table], rows=len(actual_rows))
    observations = {source['id']: _native_observation(evidence, source, executions[source['execution_id']]) for source in sources.values()}
    check('来源严格释放及边界', all(source['released_at'] is not None and source['start_permitted'] == 1
        and source['execution_error'] is None and observations[source['id']]['complete'] for source in sources.values()), sources=len(sources))
    deliveries_by_id = {row['id']: row for row in deliveries}
    for source in sources.values():
        execution = executions[source['execution_id']]
        delivery = deliveries_by_id.get(source['delivery_id'])
        valid = bool(delivery) and delivery['task_id'] == execution['task_id']
        valid = valid and delivery['status'] == 'consumed' and delivery['consumed_source_id'] == source['id']
        valid = valid and delivery['consumed_at'] is not None and _digest(delivery['prompt']) == delivery['input_digest']
        valid = valid and _input_text(evidence, source, execution, delivery['input_key']) == delivery['prompt']
        check('全部实际输入投递来源_' + str(source['id']), valid, role=execution['role'], delivery_id=source['delivery_id'])
    branch_rows, consumed_branches = [], set()
    for delivery in deliveries:
        if not delivery['phase_key'].startswith('disclosure:'):
            continue
        task = tasks[delivery['task_id']]
        branch_id = delivery['phase_key'].removeprefix('disclosure:')
        # disclosure 行是材料披露意图，实际消费记录在随后独立的 candidate 投递行。
        candidates = [row for row in deliveries if row['task_id'] == task['id'] and row['phase_key'].startswith('candidate:')
            and row['prompt'] == delivery['prompt'] and row['status'] == 'consumed' and row['consumed_at'] is not None and row['input_key']]
        consumed_sources = []
        for candidate in candidates:
            source = sources.get(candidate['consumed_source_id'])
            if source is None:
                continue
            execution = executions[source['execution_id']]
            records = observations[source['id']]['records']
            if execution['task_id'] == task['id'] and execution['role'] == 'candidate' and any(record.get('type') == 'user'
                    and record.get('message', {}).get('content') == delivery['prompt'] for record in records):
                consumed_sources.append(source['id'])
        consumed = bool(consumed_sources) and _digest(delivery['prompt']) == delivery['input_digest']
        check('披露实际消费_' + str(delivery['id']), consumed, task_id=task['id'], task_key=task['task_key'], branch_id=branch_id,
            consumed_source_ids=consumed_sources)
        consumed_branches.add((task['task_key'], branch_id))
        branch_rows.append({'task_id': task['id'], 'task_key': task['task_key'], 'branch_id': branch_id, 'delivery_id': delivery['id'],
            'consumed_source_ids': consumed_sources, 'business_attempt_count': task['attempt_count']})
    check('全部冻结分支已消费', consumed_branches == expected_branches,
        expected=sorted(expected_branches), actual=sorted(consumed_branches))
    for task in selected:
        scene = scenes[task['scenario_instance_id']]
        instance = instances[scene['instance_id']]
        route = (instance['batch_id'], instance['project_key'], scene['scenario_key'], scene['entry_key'], task['task_key'])
        requests = expected_context.get(route, [])
        actual_branches = [row for row in branch_rows if row['task_id'] == task['id']]
        valid = [row['branch_id'] for row in actual_branches] == [request['branch_id'] for request in requests]
        for branch_row, request in zip(actual_branches, requests):
            delivered = next(row for row in deliveries if row['id'] == branch_row['delivery_id'])
            valid = valid and all(fragment in delivered['prompt'] for fragment in request['material_fragments'])
        check('逐路径必要材料消费_' + str(task['id']), valid, task_key=task['task_key'],
            expected=[request['branch_id'] for request in requests], actual=[row['branch_id'] for row in actual_branches])
    attempts_api = {item['task_id']: item['attempts'] for item in attempts}
    attempt_rows = defaultdict(list)
    for item in facts['project_task_attempts']:
        attempt_rows[item['task_id']].append(item)
    check('正常披露不增加业务尝试', all(task['attempt_count'] == 1 and len(attempt_rows[task['id']]) == 1
        and len(attempts_api.get(task['id'], [])) == 1 and attempt_rows[task['id']][0]['attempt_no'] == 1
        and attempt_rows[task['id']][0]['result'] == 'passed' and attempt_rows[task['id']][0]['ended_at'] is not None for task in selected),
        selected_paths=len(selected), actual_attempts=len(facts['project_task_attempts']), disclosure_deliveries=len(branch_rows))
    check('候选实际执行绑定本任务业务尝试', all(execution['attempt_id'] in {row['id'] for row in attempt_rows[execution['task_id']]}
        for execution in executions.values() if execution['role'] == 'candidate'))
    readonly = [task for task in selected if task['kind'] != 'modify']
    modifications = [task for task in selected if task['kind'] == 'modify']
    check('只读任务不接受代码检查点', all(task['accepted_checkpoint_digest'] is None for task in readonly), readonly_paths=len(readonly))
    accepted_modifications = [task for task in modifications if task['accepted_checkpoint_digest']]
    expected_modify_paths = sum(1 for path in expected_paths if next(task for scene in project_manifests[path[1]]['scenarios'] for task in scene['tasks'] if task['id'] == path[-1])['kind'] == 'modify')
    check('全部修改目标及重复入口接受', len(modifications) == expected_modify_paths and {task['task_key'] for task in modifications} == set(native_contracts)
        and len(accepted_modifications) == expected_modify_paths, accepted_paths=len(accepted_modifications),
        targets=dict(Counter(task['task_key'] for task in modifications)))

    verified_manifests, verified_objects = {}, set()

    def manifest(digest: str) -> dict:
        """核对完整清单及对象字节，缓存只减少重复读取。"""
        if digest not in verified_manifests:
            snapshot = _read(evidence / 'project-artifacts/manifests' / (digest + '.json'))
            if snapshot['digest'] != digest or _digest(snapshot['files']) != digest:
                raise ValueError('候选／父链清单摘要不符：' + digest)
            for item in snapshot['files'].values():
                object_digest = item['digest']
                if object_digest in verified_objects:
                    continue
                path = evidence / 'project-artifacts/objects' / object_digest[:2] / object_digest
                if path.is_symlink() or not path.is_file() or path.stat().st_size != item['size'] or sha256(path.read_bytes()).hexdigest() != object_digest:
                    raise ValueError('冻结对象字节摘要不符：' + object_digest)
                verified_objects.add(object_digest)
            verified_manifests[digest] = snapshot
        return verified_manifests[digest]

    parent_chain = []
    for job in jobs.values():
        task = tasks[job['task_id']]
        scene = scenes[task['scenario_instance_id']]
        instance = instances[scene['instance_id']]
        project_root = catalog / 'projects' / instance['project_key']
        definition = _parse(task['definition_json'])
        evidence_row = _parse(job['evidence_json'])
        source = sources[job['source_id']]
        execution = executions[source['execution_id']]
        parent_id = evidence_row['parent_code_job_id']
        parent = jobs.get(parent_id)
        if parent_id is not None:
            parent_task = tasks[parent['task_id']] if parent else None
            check('代码父链归属_' + str(job['id']), bool(parent_task) and parent_task['scenario_instance_id'] == task['scenario_instance_id']
                and parent_task['kind'] == 'modify' and parent_task['status'] == 'passed' and parent['status'] == 'passed'
                and parent_task['accepted_checkpoint_digest'] == parent['candidate_digest'] == evidence_row['parent_code_digest']
                and parent['ended_at'] is not None and parent['ended_at'] <= source['created_at'], parent_job_id=parent_id)
        if not definition['requires']:
            base_files = manifest(evidence_row['parent_code_digest'])['files']
            seed_files = manifest(scenes[task['scenario_instance_id']]['seed_digest'])['files']
            library_before = {name: value for name, value in base_files.items() if name.startswith('library/')}
            library_seed = {name: value for name, value in seed_files.items() if name.startswith('library/')}
            check('独立场景基线_' + str(job['id']), parent_id is None and library_before == library_seed,
                task_key=task['task_key'], parent_job_id=parent_id, library_files=len(library_before))
        candidate_snapshot = manifest(job['candidate_digest'])
        input_snapshot = manifest(evidence_row['input_checkpoint_digest'])
        manifest(evidence_row['parent_code_digest'])
        mechanical = _parse(job['native_result_json'])
        if mechanical is not None:
            changed = sorted(name for name in candidate_snapshot['files'].keys() | input_snapshot['files'].keys()
                if candidate_snapshot['files'].get(name) != input_snapshot['files'].get(name))
            prefixes = _parse(task['definition_json'])['allowed_paths']
            unauthorized = [name for name in changed if not any(name == prefix.rstrip('/') or name.startswith(prefix.rstrip('/') + '/') for prefix in prefixes)]
            check('候选真实差异和授权范围_' + str(job['id']), changed == mechanical['changed_files']
                and unauthorized == mechanical['unauthorized_files'] and not unauthorized,
                task_key=task['task_key'], changed_files=changed)
        answer = _read(evidence / job['answer_relative'])['text']
        check('回答来源摘要_' + str(job['id']), _digest(answer) == job['response_digest']
            and _response_text(evidence, source, execution, job['response_key']) == answer
            and evidence_row['request']['source'] == source['source'] and evidence_row['request']['run_id'] == execution['run_id']
            and evidence_row['request']['step_id'] == task['task_key'] and evidence_row['request']['response_key'] == job['response_key']
            and execution['task_id'] == task['id'])
        rubric = _read(project_root / definition['evaluation']['rubric'])
        defaults = rubric.get('source_evidence', {})
        references = [item for rows in defaults.values() for item in rows] if isinstance(defaults, dict) else []
        for criterion in rubric['criteria']:
            criterion.setdefault('evidence', references)
        package = _read(evidence / 'project-artifacts/evaluations' / str(job['id']) / 'input.json')
        identity = {key: job[key] for key in ('task_id', 'turn_no', 'response_digest', 'basis_digest')}
        identity['job_id'] = job['id']
        candidate_files = {}
        for relative in mechanical['changed_files']:
            item = candidate_snapshot['files'].get(relative)
            if item is None:
                candidate_files[relative] = {'deleted': True}
            else:
                raw = (evidence / 'project-artifacts/objects' / item['digest'][:2] / item['digest']).read_bytes()
                try:
                    text = raw.decode('utf-8')
                except UnicodeDecodeError:
                    text = None
                candidate_files[relative] = {**item, 'text': text, 'binary': text is None}
        check('完整评审输入和依据摘要_' + str(job['id']),
            all(package[key] == value for key, value in identity.items())
            and package['rubric'] == rubric and _digest(rubric) == job['basis_digest']
            and package['answer'] == answer and _digest(package['conversation']) == job['input_digest']
            and package['conversation'] == evidence_row['conversation']
            and package['question'] == next(item['content'] for item in package['conversation'] if item['role'] == 'user')
            and package['native_result'] == mechanical and package['candidate_files'] == candidate_files
            and package['source_files'] == source_files(project_root, rubric)
            and package['permissions'] == {'allowed_paths': definition['allowed_paths'], 'task_id': definition['id']}
            and package['outcomes'] == definition['outcomes'] and package['resolved_model'] == evidence_row['resolved_model'],
            candidate_file_count=len(candidate_files), conversation_rows=len(package['conversation']))
        review = _parse(job['review_result_json'])
        if review is not None:
            review_source = sources[review['source_id']]
            review_execution = executions[review_source['execution_id']]
            review_answer = loads(_response_text(evidence, review_source, review_execution, review['response_key']))
            check('评审来源及冻结回答归属_' + str(job['id']), review_execution['role'] == 'review'
                and review_execution['evaluation_job_id'] == job['id'] and review_execution['task_id'] == task['id']
                and review_answer == review['decision'] and review['decision']['response_digest'] == job['response_digest']
                and review['decision']['basis_digest'] == job['basis_digest'])
            decision = review['decision']
            rules = {item['id']: item for item in rubric['criteria']}
            criterion_ids = [item['id'] for item in decision['criteria']]
            valid = len(criterion_ids) == len(set(criterion_ids)) == len(rules) and set(criterion_ids) == set(rules)
            valid = valid and all(decision[key] == value for key, value in identity.items())
            for criterion in decision['criteria']:
                rule = rules[criterion['id']]
                references = criterion['evidence']
                valid = valid and all(reference in rule['evidence'] and reference in package['source_files']
                    or rule.get('allow_candidate_evidence') is True and reference.startswith('candidate:')
                    and reference.removeprefix('candidate:') in candidate_files for reference in references)
                valid = valid and (not (rule['evidence'] or rule.get('allow_candidate_evidence'))
                    or criterion['status'] not in ('satisfied', 'violated') or bool(references))
            if decision['decision'] == 'pass':
                valid = valid and mechanical['status'] == 'passed' and decision['outcome'] in definition['outcomes']
                valid = valid and decision['branch_id'] is None and all(item['status'] == 'satisfied' for item in decision['criteria'])
            elif decision['decision'] == 'disclose':
                valid = valid and decision['outcome'] is None and decision['branch_id'] in {
                    item['id'] for item in package['allowed_branches']}
            else:
                valid = False
            valid = valid and all(code in package['feedback_codes'] for code in decision['feedback_codes'])
            check('评审逐项冻结证据与合法结论_' + str(job['id']), valid,
                decision=decision['decision'], criterion_count=len(criterion_ids))
    # answer依赖不产生代码父链，必须在同场景原生session前缀中实际保留已接受答案。
    answer_dependencies = []
    for task in selected:
        definition = _parse(task['definition_json'])
        for dependency in definition['requires']:
            if dependency['artifact'] != 'answer':
                continue
            target = next(item for item in selected if item['scenario_instance_id'] == task['scenario_instance_id']
                and item['task_key'] == dependency['task_id'])
            target_jobs = [item for item in jobs.values() if item['task_id'] == target['id'] and item['status'] == 'passed']
            current_jobs = [item for item in jobs.values() if item['task_id'] == task['id']]
            valid = target['status'] == 'passed' and bool(target_jobs) and bool(current_jobs)
            for current in current_jobs:
                current_source = sources[current['source_id']]
                current_execution = executions[current_source['execution_id']]
                previous = max(target_jobs, key=lambda item: item['ended_at'])
                previous_source = sources[previous['source_id']]
                previous_execution = executions[previous_source['execution_id']]
                name = current_execution['session_id'] + '.jsonl'
                prefix = (evidence / 'native-sessions' / str(current_source['id']) / name).read_bytes()[
                    :_parse(current_source['evidence_start_json']).get(name, 0)]
                previous_answer = _read(evidence / previous['answer_relative'])['text']
                prefix_answers = [record['message'].get('content') for line in prefix.splitlines()
                    if (record := loads(line)).get('type') == 'assistant']
                texts = ['\n'.join(item['text'] for item in value if item.get('type') == 'text')
                    if isinstance(value, list) else value for value in prefix_answers]
                valid = valid and previous['ended_at'] <= current_source['created_at']
                valid = valid and current_execution['session_id'] == previous_execution['session_id'] and previous_answer in texts
                answer_dependencies.append({'task_id': task['id'], 'task_key': task['task_key'],
                    'dependency_task_id': target['id'], 'dependency_evaluation_id': previous['id'],
                    'evaluation_id': current['id'], 'source_id': current_source['id']})
            check('已接受答案真实上下文消费_' + str(task['id']), valid, dependency_task_id=target['id'])
    for task in accepted_modifications:
        accepted = [job for job in jobs.values() if job['task_id'] == task['id'] and job['candidate_digest'] == task['accepted_checkpoint_digest']
            and job['status'] == 'passed' and _parse(job['review_result_json'])['decision']['decision'] == 'pass']
        contract = native_contracts[task['task_key']]
        collection_digest = _digest([{'id': node['id'], 'kind': node['kind']} for node in contract['nodes']])
        valid = bool(accepted)
        for job in accepted:
            report = _parse(job['native_result_json'])
            native = report.get('native', {})
            regression = native.get('regression', {})
            actual = regression.get('regression', {})
            valid = valid and report['status'] == native.get('status') == native.get('business', {}).get('status') == regression.get('status') == actual.get('status') == 'passed'
            valid = valid and regression.get('contract_digest') == _digest(contract) and actual.get('collection_matches_contract') is True
            valid = valid and actual.get('collected') == len(contract['nodes']) and actual.get('collection_digest') == collection_digest
            valid = valid and actual.get('result_digest') == _digest(contract['nodes'])
            valid = valid and actual.get('xml_testcases') == len(contract['nodes'])
            valid = valid and sum(actual.get('counts', {}).values()) == len(contract['nodes'])
            if contract.get('subtests'):
                valid = valid and bool(contract['subtests'])
                valid = valid and actual.get('subtests') == contract['subtests']
                valid = valid and actual.get('subtest_count') == len(contract['subtests']) and actual.get('subtests_match_contract') is True
                valid = valid and all(item['parent_nodeid'] in {node['id'] for node in contract['nodes']}
                    for item in actual['subtests'])
        check('已接受修改的独立验收_' + str(task['id']), valid, task_key=task['task_key'], expected_native_nodes=len(contract['nodes']))
    for artifact in artifacts:
        if artifact['evaluation_id'] is None:
            continue
        task, job = tasks[artifact['task_id']], jobs[artifact['evaluation_id']]
        snapshot = manifest(job['candidate_digest'])
        files = {item['path']: {key: value for key, value in item.items() if key != 'path'} for item in artifact['files']}
        check('成果摘要与接受状态_' + str(task['id']), artifact['candidate_digest'] == job['candidate_digest']
            and artifact['response_digest'] == job['response_digest'] and files == snapshot['files']
            and artifact['code_accepted'] == (task['accepted_checkpoint_digest'] == job['candidate_digest']))

    private_observations = _read(evidence / 'private-review-observations.json')
    review_sources = {row['source']: row for row in sources.values()
        if executions[row['execution_id']]['role'] == 'review'}
    check('逐评审隔离观测来源全集', len(private_observations) == len(review_sources)
        and {row['source'] for row in private_observations} == set(review_sources),
        observations=len(private_observations), review_sources=len(review_sources))
    for observation in private_observations:
        source = review_sources[observation['source']]
        execution = executions[source['execution_id']]
        job = jobs[execution['evaluation_job_id']]
        relative = Path(observation['package_relative'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('私有评审包路径越界')
        raw = (evidence / relative).read_bytes()
        package = loads(raw)
        saved_package = _read(evidence / 'project-artifacts/evaluations' / str(job['id']) / 'input.json')
        mounts = observation['candidate_mounts']
        private = Path(observation['private_root'])
        mapped = Path(observation['host_data_root']) / Path(observation['private_runtime_root']).relative_to(
            Path(observation['runtime_data_root']))
        not_mounted = not any(private == Path(row['Source']) or private.is_relative_to(Path(row['Source']))
            or Path(row['Source']).is_relative_to(private) for row in mounts)
        valid = observation['run_id'] == execution['run_id'] and observation['evaluation_job_id'] == job['id']
        valid = valid and observation['task_id'] == job['task_id'] and observation['source'] == source['source']
        valid = valid and observation['package_sha256'] == sha256(raw).hexdigest() and package == saved_package
        valid = valid and observation['response_digest'] == package['response_digest'] == job['response_digest']
        valid = valid and observation['basis_digest'] == package['basis_digest'] == job['basis_digest']
        valid = valid and observation['resolved_model'] == package['resolved_model'] == 'offline-fixture'
        valid = valid and observation['readonly_root'] is True and observation['user'] == '1000:1000'
        valid = valid and observation['cap_drop'] == ['ALL']
        valid = valid and observation['network_mode'] == observation['expected_network_mode']
        valid = valid and observation['network_mode'].startswith('container:')
        valid = valid and observation['candidate_container_id'] != observation['review_container_id']
        valid = valid and observation['candidate_pid_namespace'] != observation['review_pid_namespace']
        valid = valid and observation['candidate_pid_namespace'].startswith('pid:[')
        valid = valid and observation['review_pid_namespace'].startswith('pid:[')
        valid = valid and observation['candidate_input_visibility_exit_code'] != 0
        valid = valid and private == mapped and not_mounted and observation['private_not_mounted'] is True
        valid = valid and observation['candidate_mounts_sha256'] == sha256(dumps(mounts, sort_keys=True).encode()).hexdigest()
        valid = valid and 'claudeAiOauth' in observation['credential_top_keys']
        valid = valid and 'accessToken' in observation['oauth_credential_keys'] and 'refreshToken' not in observation['oauth_credential_keys']
        check('实际私有评审隔离_' + str(source['id']), valid, run_id=execution['run_id'], job_id=job['id'],
            package_sha256=observation['package_sha256'], candidate_mount_count=len(mounts))

    # source.released_at在真实holder释放、调度sem释放及尾部取证以后写入，不是holder终点。
    # 保留其重叠诊断，容量另用同boot原生单调工作区间和逐进程清理事实核对。
    accounting_events = [(row['created_at'], 1, row['id']) for row in sources.values()] + [
        (row['released_at'], -1, row['id']) for row in sources.values()]
    active_sources, maximum_accounting = set(), 0
    overlaps = []
    accounting_events.sort()
    for index, (at, change, source_id) in enumerate(accounting_events):
        active_sources.add(source_id) if change == 1 else active_sources.remove(source_id)
        maximum_accounting = max(maximum_accounting, len(active_sources))
        if len(active_sources) > 2:
            until = accounting_events[index + 1][0]
            overlaps.append({'start_wall': at, 'end_wall': until, 'duration_sec': until - at,
                'sources': [{'id': identifier, 'source': sources[identifier]['source'],
                    'run_id': executions[sources[identifier]['execution_id']]['run_id'],
                    'role': executions[sources[identifier]['execution_id']]['role']}
                    for identifier in sorted(active_sources)]})
    work_events = []
    process_count = 0
    for source in sources.values():
        execution = executions[source['execution_id']]
        base = evidence / 'execution-diagnostics' / execution['run_id'] / str(source['id'])
        timer = _read(base / 'runtime/project-work.json')
        process, ended = _read(base / 'driver/process.json'), _read(base / 'driver/process-result.json')
        identity = {key: process[key] for key in ('schema', 'pid', 'started', 'source', 'parent', 'uid')}
        check('原生监督进程严格退出_' + str(source['id']), all(ended[key] == value for key, value in identity.items())
            and process['source'] == source['source'] and process['uid'] == 1000
            and ended['cleaned'] is True and ended['exit_code'] == 0,
            source=source['source'], process_pid=process['pid'], cleaned=ended['cleaned'], exit_code=ended['exit_code'])
        process_count += 1
        work_events.extend([(timer['boot_id'], timer['started_mono'], 1),
            (timer['boot_id'], timer['started_mono'] + timer['elapsed_sec'], -1)])
    active_work, maximum_work = {}, {}
    for boot, at, change in sorted(work_events):
        active_work[boot] = active_work.get(boot, 0) + change
        maximum_work[boot] = max(maximum_work.get(boot, 0), active_work[boot])
    check('原生单调工作区间共享容量', bool(maximum_work) and max(maximum_work.values()) == 2
        and all(value == 0 for value in active_work.values()) and result['maximum_holders'] == 2,
        maximum_work_by_boot=maximum_work, reported_sampled_holders=result['maximum_holders'],
        cleaned_processes=process_count)
    capacity_evidence = {'source_accounting_maximum': maximum_accounting, 'source_accounting_overlaps': overlaps,
        'work_maximum_by_boot': maximum_work, 'observed_sampled_holders': result['maximum_holders'],
        'strictly_cleaned_processes': process_count, 'exact_holder_intervals_reconstructed': False,
        'limitation': '未持久保存逐holder claim/release事件，不能重建其纳秒区间。source记账尾部包含释放后的取证延迟。',
        'ordering_evidence': ['account_runtime.py:1030-1077 环境锁/登记锁下先核siblings<cli_limit再登记',
            'project_review_runtime.py:396-425 claim后才创建execution_configuration/source',
            'account_runtime.py:1783-1812 先停止私有进程/容器，再release/remove holder',
            'account_runtime.py:1157-1200 严格退出证明后释放租约并移除holder',
            'main.py:7035-7069 cleanup后释放sem，再execution_released回调',
            'project_scenarios.py:831-855 回调核输入/计时后最后写released_at']}

    task_observations = defaultdict(list)
    task_segments = defaultdict(list)
    for source in sources.values():
        execution = executions[source['execution_id']]
        task_observations[(execution['task_id'], execution['role'])].append(observations[source['id']])
    for segment in facts['project_work_segments']:
        execution = executions[sources[segment['source_id']]['execution_id']]
        task_segments[(execution['task_id'], segment['role'])].append(segment)
        timer = _read(evidence / 'execution-diagnostics' / execution['run_id'] / str(segment['source_id']) /
            'runtime/project-work.json')
        check('原生单调计时片段_' + str(segment['id']), timer['source'] == sources[segment['source_id']]['source']
            and timer['segment_id'] == segment['id'] and timer['boot_id'] == segment['boot_id']
            and timer['settled'] is True and segment['status'] == 'settled'
            and timer['started_mono'] >= segment['start_mono']
            and 0 <= segment['confirmed_sec'] <= segment['reserved_sec'] + 3
            and isclose(timer['elapsed_sec'], segment['confirmed_sec'], rel_tol=0, abs_tol=0.000001),
            elapsed_sec=timer['elapsed_sec'], confirmed_sec=segment['confirmed_sec'], reserved_sec=segment['reserved_sec'])
    usage_tasks = {task['id']: task for instance in usage['instances'] for task in instance['tasks']}
    totals = {}
    for task in tasks.values():
        scene = scenes[task['scenario_instance_id']]
        instance = instances[scene['instance_id']]
        policy = _parse(batches[instance['batch_id']]['policy_json'])
        for role in ('candidate', 'review'):
            actual = _aggregate(task_observations[(task['id'], role)])
            reported = usage_tasks[task['id']]['roles'][role]
            check('角色计量_' + str(task['id']) + '_' + role, actual == {key: reported[key] for key in actual},
                sources=actual['sources'], known_sources=actual['known_sources'], complete=actual['complete'])
            rows = task_segments[(task['id'], role)]
            confirmed = sum(row['confirmed_sec'] for row in rows)
            reserved = sum(max(0, row['reserved_sec'] - row['confirmed_sec']) for row in rows if row['status'] != 'settled')
            limit = policy['task_budget_sec' if role == 'candidate' else 'review_budget_sec']
            budget = {'confirmed_sec': confirmed, 'reserved_sec': reserved, 'remaining_sec': max(0, limit-confirmed-reserved),
                'slice_sec': min(max(0, limit-confirmed-reserved), policy['timeout_sec']) if role == 'candidate' else None,
                'uncertain': any(row['status'] == 'uncertain' for row in rows)}
            check('角色预算_' + str(task['id']) + '_' + role, _same_budget(budget, reported['work'])
                and _same_budget(budget, public[task['id']][role + '_budget']))
    for role in ('candidate', 'review'):
        role_sources = [observations[source['id']] for source in sources.values() if executions[source['execution_id']]['role'] == role]
        totals[role] = _aggregate(role_sources)
    for instance_usage in usage['instances']:
        instance_id = instance_usage['instance_id']
        for group in instance_usage['by_kind']:
            group_observations = [observation for (task_id, role), values in task_observations.items() for observation in values
                if role == group['role'] and tasks[task_id]['kind'] == group['kind']
                and scenes[tasks[task_id]['scenario_instance_id']]['instance_id'] == instance_id]
            actual = _aggregate(group_observations)
            check('分类角色计量_' + str(instance_id) + '_' + group['kind'] + '_' + group['role'], actual == {key: group[key] for key in actual})
    check('时间片完整结算', all(row['status'] == 'settled' and row['settled_at'] is not None for row in facts['project_work_segments']),
        status_counts=dict(Counter(row['status'] for row in facts['project_work_segments'])))
    review_charges, attempt_charges = defaultdict(float), defaultdict(float)
    for segment in facts['project_work_segments']:
        if segment['role'] != 'review':
            continue
        execution = executions[sources[segment['source_id']]['execution_id']]
        charge = segment['confirmed_sec'] if segment['status'] == 'settled' else max(segment['confirmed_sec'], segment['reserved_sec'])
        review_charges[execution['evaluation_job_id']] += charge
        attempt_charges[(execution['evaluation_job_id'], execution['review_attempt'])] += charge
    for job_id, charge in review_charges.items():
        check('冻结回答评审预算_' + str(job_id), charge <= jobs[job_id]['response_budget_sec'],
            charged_sec=charge, limit_sec=jobs[job_id]['response_budget_sec'])
    for (job_id, review_attempt), charge in attempt_charges.items():
        task = tasks[jobs[job_id]['task_id']]
        policy = _parse(batches[instances[scenes[task['scenario_instance_id']]['instance_id']]['batch_id']]['policy_json'])
        check('逻辑评审尝试预算_' + str(job_id) + '_' + str(review_attempt), review_attempt in (1, 2) and charge <= policy['review_timeout_sec'],
            charged_sec=charge, limit_sec=policy['review_timeout_sec'])
    assistant_records = [record for observation in observations.values() for record in observation['records'] if record.get('type') == 'assistant']
    check('真实推理为零且身份均为替身', runtime['model_calls'] == 0 and result['real_model_calls'] == 0 and result['real_oauth_calls'] == 0
        and result['synthetic'] is True and usage['synthetic'] is True and usage['measurement'] == 'fixture-native-log'
        and all(row['execution_model'] == 'offline-fixture' and row['claude_code_version'] == '9.9.9'
            and row['claude_effort_level'] == 'high' for row in facts['runs'])
        and all(by_table['runs'][execution['run_id']]['run_kind'] == ('project_iteration' if execution['role'] == 'candidate' else 'project_review')
            for execution in executions.values())
        and all(record.get('simulation') is True and record.get('message', {}).get('model') == 'offline-fixture' for record in assistant_records)
        and all(_parse(job['evidence_json'])['resolved_model'] == 'offline-fixture' for job in jobs.values())
        and all(_parse(job['review_result_json'])['observed_model'] == 'offline-fixture' for job in jobs.values() if job['review_result_json']),
        runs=len(facts['runs']), real_model_calls=result['real_model_calls'], real_oauth_calls=result['real_oauth_calls'])
    inventory_after = inventory(evidence)
    check('审计前后完整证据字节不变', inventory_before == inventory_after, files=len(inventory_after))
    return {'schema': 1, 'status': 'failed' if failures else 'passed', 'run': str(run), 'evidence': str(evidence),
        'snapshot': 'archived' if evidence == run / 'evidence' else 'live_ready', 'browser_status': result.get('browser_status'),
        'scope': '独立只读模拟数据审计；不是正式 Check-All 或真实模型质量评估',
        'summary': {'stage_selected_counts': stage_counts, 'selected_paths': len(selected), 'unique_tasks': len({row['task_key'] for row in selected}),
            'stored_task_rows': len(tasks), 'unselected_task_rows': len(tasks) - len(selected), 'instances': len(instances), 'batches': len(batches),
            'unique_task_kinds': dict(Counter({row['task_key']: row['kind'] for row in selected}.values())),
            'readonly_paths': len(readonly), 'selected_modify_paths': len(modifications), 'code_acceptances': len(accepted_modifications),
            'unique_modify_targets': len({row['task_key'] for row in accepted_modifications}),
            'unavailable_paths': len(unavailable), 'disclosure_deliveries': len(branch_rows), 'runs': len(facts['runs']),
            'frozen_manifests_verified': len(verified_manifests), 'frozen_objects_verified': len(verified_objects),
            'private_review_observations': len(private_observations), 'maximum_work_intervals': max(maximum_work.values()),
            'sampled_maximum_holders': result['maximum_holders'], 'source_accounting_maximum': maximum_accounting,
            'answer_dependencies': len(answer_dependencies), 'evidence_files': len(inventory_after)},
        'fixture_hash_observation': '本次只读审计时读取，不宣称是运行前单独封存的配方摘要',
        'stage_configuration_sha256': sha256(stages_path.read_bytes()).hexdigest(), 'fixture_sha256': fixture_sha256,
        'role_usage': totals, 'code_parent_chain': parent_chain, 'disclosures': branch_rows,
        'answer_dependencies': answer_dependencies, 'evidence_inventory_digest': _digest(inventory_after),
        'capacity_evidence': capacity_evidence,
        'real_model_quality_assessed': False, 'real_model_calls': result['real_model_calls'], 'checks': checks, 'failures': failures}


def main() -> None:
    """解析只读审计入口，只向指定审计结果文件写报告。

    :return: None；失败退出 1，证据未完成退出 2。
    """
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--catalog', type=Path, default=Path(__file__).resolve().parents[2] / 'project_library')
    parser.add_argument('--stages', type=Path, default=Path(__file__).resolve().parent / 'fixtures/stages.json')
    parser.add_argument('--snapshot', type=Path, help='创建独立完整快照后仅审计副本，不覆盖既有目录')
    parser.add_argument('--compare-snapshot', type=Path, help='核本次归档与既有完整快照的SHA和实际表')
    args = parser.parse_args()
    try:
        target = args.run.resolve()
        receipt = snapshot(target, args.snapshot.resolve()) if args.snapshot else None
        target = args.snapshot.resolve() if args.snapshot else target
        report = audit(target, args.catalog.resolve(), args.stages.resolve())
        if receipt is not None:
            report['snapshot_copy'] = {key: value for key, value in receipt.items() if key != 'files'}
        if args.compare_snapshot and report['status'] != 'pending':
            comparison = compare_snapshot(select_evidence(target), args.compare_snapshot.resolve())
            report['snapshot_comparison'] = comparison
            if comparison['status'] != 'passed':
                report['status'] = 'failed'
                report['failures'].append({'check': '最终归档与独立快照', 'status': 'failed', **comparison})
    except Exception as error:
        report = {'schema': 1, 'status': 'failed', 'run': str(args.run), 'error': type(error).__name__ + ': ' + str(error),
            'scope': '独立只读模拟数据审计；不是正式 Check-All', 'real_model_quality_assessed': False}
    args.output.write_text(dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(dumps({key: value for key, value in report.items() if key in ('status', 'summary', 'reason', 'error')}, ensure_ascii=False))
    raise SystemExit(0 if report['status'] == 'passed' else 2 if report['status'] == 'pending' else 1)


if __name__ == '__main__':
    main()
