"""用临时合成数据库核百项目公开API、暂停批次及冻结历史读取。"""

from argparse import ArgumentParser
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[4]
RESEARCH = Path(__file__).resolve().parent


def require(condition: bool, message: str) -> None:
    """保留优化模式下的校验。@param condition 条件。@param message 错误。@return None。"""
    if not condition:
        raise ValueError(message)


def evidence(path: Path) -> dict:
    """记录证据原件摘要。@param path 文件。@return 路径与SHA。"""
    return {'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main() -> None:
    """运行真实控制器探针并清理其数据副本。@return None。"""
    started = time.monotonic()
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', required=True, type=int)
    attempt = parser.parse_args().attempt
    require(attempt > 0, '尝试号必须为正整数')
    output = ROOT / '.deploy/project-catalog-hundred/final-integration' / f'api-attempt-{attempt:03d}'
    output.mkdir(parents=True, exist_ok=False)
    calls = []
    observed = {}
    managers = []
    client = None
    temporary = tempfile.TemporaryDirectory(prefix='synthetic-data-', dir=output)
    data = Path(temporary.name)
    try:
        # 导入前绑定所有持久路径，避免控制器默认数据目录或真实账号参与探针。
        os.environ.update(BENCH_DATA=str(data), HOST_BENCH_DATA=str(data),
            TOPICS_FILE=str(ROOT / 'topics.md'), PROJECT_LIBRARY_DIR=str(ROOT / 'project_library'),
            WEBUI_USER='', WEBUI_PASS='', V3_DEPLOYMENT_ID='')
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(ROOT / 'orchestrator'))
        from fastapi.testclient import TestClient
        import main as controller
        from project_iteration import ProjectIterationManager
        from project_library import ProjectLibrary

        def forbidden(*args, **kwargs):
            """一旦触发执行即失败，防元数据探针误投放。@return 永不返回。"""
            calls.append('unexpected_execution')
            raise RuntimeError('暂停批次探针禁止候选、评审和验收执行')

        def make_manager(library):
            """构造无后台线程的真实管理器。@param library 当前库或None。@return 管理器。"""
            verifier = Mock(verify=forbidden, verify_native=forbidden)
            manager = ProjectIterationManager(data, library, controller.get_db, controller._db_lock,
                forbidden, lambda: {'claude_code_version': '2.1.293',
                    'claude_effort_level': 'xhigh', 'execution_model': 'opus'},
                lambda account: 'synthetic-final-' + str(account['id']), forbidden, verifier,
                lambda rid, attempt: False)
            managers.append(manager)
            return manager

        controller.init_db()
        require(controller.DB_PATH == data / 'db.sqlite', '数据库路径未隔离')
        with controller._db_lock:
            connection = controller.get_db()
            try:
                with connection:
                    connection.execute('INSERT INTO accounts(id,name,profile_path) VALUES(?,?,?)',
                        (1, 'synthetic-final-only', 'synthetic-final-only'))
            finally:
                connection.close()
        library = ProjectLibrary(ROOT / 'project_library')
        require(len(library.projects) == 100, '实际目录不是一百项目')
        manager = make_manager(library)
        expected_scenes = sum(len(p.manifest['scenarios']) for p in library.projects.values())
        expected_tasks = sum(len(s['tasks']) for p in library.projects.values() for s in p.manifest['scenarios'])
        expected_selected = sum(len(next(e for e in s['entries'] if e['id'] == s['default_entry'])['task_ids'])
            for p in library.projects.values() for s in p.manifest['scenarios'])
        require((expected_scenes, expected_tasks) == (426, 726), '实际内容计数变化')
        with patch.multiple(controller, project_iterations=manager, _AUTH_ENABLED=False, V3_ENABLED=False):
            # 不进入TestClient生命周期，真实调度线程与外部服务均不会启动。
            client = TestClient(controller.app)
            response = client.get('/api/project-catalog')
            require(response.status_code == 200, '目录读取失败')
            catalog = response.json()
            require(catalog == manager.catalog(), '目录公开投影变化')
            require(catalog['digest'] == library.digest and catalog['content_schema'] == 2, '目录版本错误')
            require(len({p['project_key'] for p in catalog['projects']}) == 100, '目录项目重复')
            observed['catalog'] = catalog
            observed['details'] = {}
            for key, project in library.projects.items():
                response = client.get('/api/project-catalog/' + key)
                require(response.status_code == 200, '详情失败：' + key)
                actual = response.json()
                require(actual == project.summary(include_steps=True), '详情投影不符：' + key)
                for scene in actual['scenarios']:
                    require(set(scene) == {'id', 'title', 'goal', 'tasks'}, '场景包含私有字段')
                    require(all(set(t) == {'id', 'kind', 'goal', 'requires'} for t in scene['tasks']),
                        '任务包含提示词、材料或私有评审字段')
                observed['details'][key] = actual
            response = client.post('/api/project-iteration-batches', json={
                'account_id': 1, 'name': '合成百项目暂停批次', 'project_keys': list(library.projects)})
            require(response.status_code == 200, '百项目批次创建失败：' + response.text[:300])
            batch = response.json()
            observed['created_batch'] = batch
            require(batch['status'] == 'paused' and len(batch['instances']) == 100, '批次不是百项目暂停状态')
            require(batch['policy']['schema'] == 3 and batch['policy']['timeout_sec'] == 600, '真实默认策略不符')
            require(sum(i['selected_task_count'] for i in batch['instances']) == expected_selected, '入口计数不符')
            require(all(i['workspace_path'] is None for i in batch['instances']), '暂停批次物化了工作区')
            before = {i['id']: manager.instance(i['id']) for i in batch['instances']}

            historical = make_manager(None)
            require(historical.library is None and not historical._libraries, '历史读取复用了当前库缓存')
            with patch.object(controller, 'project_iterations', historical):
                require(client.get('/api/project-catalog').status_code == 503, '无当前库目录应503')
                require(client.get('/api/project-catalog/sqlglot').status_code == 503, '无当前库详情应503')
                require(client.post('/api/project-iteration-batches', json={'account_id': 1}).status_code == 503,
                    '无当前库仍能创建新批次')
                response = client.get('/api/project-iteration-batches/' + str(batch['id']))
                require(response.status_code == 200 and response.json() == batch, '历史批次改变')
                observed['historical_batch'] = response.json()
                observed['historical_instances'] = {}
                for iid, original in before.items():
                    response = client.get('/api/project-instances/' + str(iid))
                    require(response.status_code == 200 and response.json() == original, '历史实例改变')
                    observed['historical_instances'][str(iid)] = response.json()
                # 详情可由冻结manifest读取；再实际重新打开冻结release，核其私有源码与依赖可用。
                require(historical._release(manager.release_id).digest == library.digest, '冻结release不可重新读取')

        connection = controller.get_db()
        try:
            tables = ['project_iteration_batches', 'project_instances', 'project_scenario_instances',
                'project_scenario_tasks', 'runs', 'project_task_attempts', 'project_task_executions',
                'project_evaluation_jobs', 'project_execution_sources', 'project_task_deliveries']
            counts = {table: connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] for table in tables}
            require([counts[t] for t in tables[:4]] == [1, 100, 426, 726], '数据库内容计数不符')
            require(all(counts[t] == 0 for t in tables[4:]), '暂停批次产生执行记录')
            for table in ['project_instances', 'project_scenario_instances']:
                require(connection.execute('SELECT COUNT(*) FROM ' + table +
                    ' WHERE workspace_relative IS NOT NULL').fetchone()[0] == 0, '暂停场景物化了目录')
            require(connection.execute('SELECT SUM(selected) FROM project_scenario_tasks').fetchone()[0]
                == expected_selected, '数据库默认入口不符')
            with sqlite3.connect(output / 'synthetic-db.sqlite') as backup:
                connection.backup(backup)
        finally:
            connection.close()
        require(not calls and all(m._thread is None for m in managers), '探针启动了执行能力')
        (output / 'api-observations.json').write_text(json.dumps(observed, ensure_ascii=False, indent=2) + '\n')
        result = {'status': 'passed', 'scope': '真实百项目API、元数据暂停批次及冻结历史读取；不代替原生和产品执行证据',
            'formal': {'version': library.version, 'digest': library.digest, 'projects': 100,
                'scenarios': expected_scenes, 'tasks': expected_tasks},
            'api_project_details': 100, 'historical_instances': 100, 'new_reader_initial_cache_empty': True,
            'current_unavailable_responses': [503, 503, 503], 'database_counts': counts,
            'default_entry_selected_tasks': expected_selected, 'execution_calls': len(calls),
            'background_threads_started': 0, 'evidence': [evidence(output / 'api-observations.json'),
                evidence(output / 'synthetic-db.sqlite')],
            'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                [ROOT / 'orchestrator' / n for n in ['main.py', 'project_library.py',
                    'project_iteration.py', 'project_scenarios.py', 'project_scenario_content.py']]},
            'script': evidence(Path(__file__)), 'real_model_calls': 0, 'real_oauth_calls': 0,
            'production_touched': False}
    finally:
        if client is not None:
            client.close()
        for manager in reversed(managers):
            manager.stop()
        temporary.cleanup()
    result.update(temporary_data_removed=not data.exists(), elapsed_sec=round(time.monotonic() - started, 3))
    (RESEARCH / 'final-api-verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'database_counts': result['database_counts'],
        'selected_tasks': expected_selected, 'elapsed_sec': result['elapsed_sec']}))


if __name__ == '__main__':
    main()
