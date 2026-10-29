"""验证双迭代捕获监督、文件保留与服务端归属，不连接真实上游。"""
import hashlib
import json
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from account_runtime import atomic_json
from capture_artifacts import capture_summary
from pi_terminal import PiTerminal
from projects import ProjectsService
from projects_api import projects_router
from projects_store import ProjectsDatabase
import test_account_runtime


class CaptureSettingsRuntimeTests(unittest.TestCase):
    """复用真实账号目录、SQLite 和登记函数，只替代 Docker 执行。"""

    def setUp(self) -> None:
        """建立独立账号环境。:return: None。"""
        self.fixture = test_account_runtime.AccountRuntimeTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.runtime = self.fixture.runtime
        self.row = self.runtime._row('synthetic', 1)
        self.row.update(container_id='capture-fixture', isolation_version=2)
        self.root = self.runtime._root(self.row)

    def test_capture_and_passthrough_use_distinct_leases_and_exact_version(self) -> None:
        """两个空间默认共享；开启时登记独占监督、CA 和真实来源。:return: None。"""
        work_id = 'a' * 32
        for namespace in ('projects', 'warmup'):
            for enabled in (False, True):
                with self.subTest(namespace=namespace, enabled=enabled):
                    account = {'id': 1, 'name': 'synthetic', 'cc2api_account_id': 7}
                    if enabled:
                        account[namespace + '_capture_enabled'] = True
                    generation = 2 if enabled else 1
                    source = f'{namespace}:{work_id}:{generation}'
                    job = {'row': self.row, 'account': account, 'source': source, 'lease': None,
                        'exclusive': False, 'shared_cli': not enabled, 'token': 'capture-fixture@' + source}
                    workspace = self.root / 'projects/synthetic'
                    workspace.mkdir(parents=True, exist_ok=True)
                    self.runtime._register_job(job)
                    terminal = PiTerminal(self.runtime, None, lambda *args: {}, namespace=namespace)
                    work = {'id': work_id, 'generation': generation, 'session_id': 'fixture-session',
                        'remaining_sec': 60, 'settings_json': json.dumps({
                            'claude_code_version': '2.1.303', 'claude_effort_level': 'high'})}
                    container = Mock(id='capture-fixture')
                    self.runtime.client.api.exec_create.return_value = {'Id': 'capture-exec'}

                    def attach(current, path):
                        current['process'] = {'schema': 1, 'source': source, 'pid': 123,
                            'started': 456, 'uid': 1000, 'parent': 0}

                    with patch.object(self.runtime, '_cli_setup', return_value=nullcontext((self.row, container, job))) as setup, \
                            patch.object(self.runtime, 'sync_credentials'), \
                            patch.object(self.runtime, '_configure_network_context') as configure, \
                            patch.object(self.runtime, '_attach_process', side_effect=attach), \
                            patch.object(terminal, '_prepare_execution', return_value=(workspace, {})):
                        info = terminal.start(account, work)
                    self.assertEqual(not enabled, setup.call_args.kwargs['shared_cli'])
                    self.assertEqual('2.1.303', setup.call_args.args[2])
                    environment = self.runtime.client.api.exec_create.call_args.kwargs['environment']
                    self.assertEqual('2.1.303', environment['CLAUDE_CODE_VERSION'])
                    self.assertIn('/cli/2.1.303/', environment['PATH'])
                    self.assertEqual(enabled, 'NODE_EXTRA_CA_CERTS' in environment)
                    self.assertEqual(enabled, info['capture_enabled'])
                    context = configure.call_args.args[1]
                    self.assertEqual('capture' if enabled else 'passthrough', context['NETWORK_INSPECTION_MODE'])
                    if enabled:
                        self.assertEqual(source, context['QUOTA_SOURCE'])
                        self.assertEqual('1', context['SAVE_FULL_FLOWS'])
                        self.assertEqual('pi-capture', job['execution_role'])
                        saved = json.loads(self.runtime._execution_path(job).read_text())
                        self.assertFalse(saved['shared_cli'])
                        self.assertIn('capture_flows', saved)
                        self.assertIn('settings_override', saved)
                    self.runtime._remove_job(job)

    def test_recorder_shutdown_retains_files_and_reports_forced_or_failed_close(self) -> None:
        """收尾只发布状态，强制退出与失败可观察，旧 HTTP 字节不减少。:return: None。"""
        directory = self.root / 'flows/group-fixture/executions/current'
        directory.mkdir(parents=True)
        raw = directory / 'http_capture.jsonl'
        raw.write_bytes(b'{"flow_id":"saved"}\n')
        original = raw.read_bytes()
        job = {'row': self.row, 'source': 'projects:fixture:1',
            'capture_flows': str(directory.relative_to(self.root / 'flows'))}
        with patch.object(self.runtime, '_configure_network_context', return_value={'previous_listener_graceful': False}):
            self.runtime._finish_capture(job, Mock())
        self.assertEqual('partial', json.loads((directory / 'capture-status.json').read_text())['state'])
        self.assertEqual(original, raw.read_bytes())
        with patch.object(self.runtime, '_configure_network_context', side_effect=ValueError('synthetic failure')):
            with self.assertRaises(ValueError):
                self.runtime._finish_capture(job, Mock())
        self.assertEqual('error', json.loads((directory / 'capture-status.json').read_text())['state'])
        self.assertEqual(original, raw.read_bytes())

    def test_summary_lists_partial_files_without_index_and_never_follows_file_links(self) -> None:
        """索引缺失不冒充文件丢失，外部链接不会进入可读清单。:return: None。"""
        directory = self.fixture.root / 'capture'
        directory.mkdir()
        (directory / 'http_capture.jsonl').write_text('{"partial":true}\n{')
        (directory / 'capture.flow').write_bytes(b'persisted-flow')
        secret = self.fixture.root / 'secret'
        secret.write_text('private')
        (directory / 'capture_index.json').symlink_to(secret)
        value = capture_summary(directory)
        self.assertEqual('partial', value['status'])
        self.assertTrue(value['available'])
        self.assertFalse(value['index_available'])
        self.assertEqual({'http_capture.jsonl', 'capture.flow'}, {item['path'] for item in value['files']})

    def test_work_capture_routes_isolate_namespaces_and_restrict_previews(self) -> None:
        """相同工作 ID 在两个空间读取不同证据，未知工作和任意路径均拒绝。:return: None。"""
        work_id = 'b' * 32
        application = FastAPI()
        for namespace, prefix in [('projects', '/api/projects'), ('warmup', '/api/accounts/warmup/pi')]:
            table = ('warmup_' if namespace == 'warmup' else '') + 'projects_work'
            with self.fixture.database() as connection:
                connection.execute(f'CREATE TABLE {table}(id TEXT, account_id INTEGER, status TEXT, settings_json TEXT)')
                connection.execute(f'INSERT INTO {table} VALUES(?,1,?,?)',
                    (work_id, 'stopped', '{"claude_code_version":"2.1.303"}'))
            directory = self.root / 'flows' / ('group-' + hashlib.sha256(f'{namespace}/{work_id}'.encode()).hexdigest()[:20])
            directory.mkdir(parents=True)
            atomic_json(directory / 'capture_index.json', {'entries': [{'flow_id': namespace,
                'request': {'headers': {'authorization': 'private'}}, 'capture_state': 'complete'}]})
            service = object.__new__(ProjectsService)
            service.database = ProjectsDatabase(self.fixture.database, namespace)
            service.data, service.namespace = self.fixture.root, namespace
            service.terminal = SimpleNamespace(runtime=self.runtime)
            application.include_router(projects_router(lambda value=service: value, prefix=prefix))
        client = TestClient(application)
        for namespace, prefix in [('projects', '/api/projects'), ('warmup', '/api/accounts/warmup/pi')]:
            path = prefix + '/work/' + work_id + '/capture'
            value = client.get(path).json()
            self.assertEqual(namespace, value['index']['entries'][0]['flow_id'])
            self.assertEqual('[redacted]', value['index']['entries'][0]['request']['headers']['authorization'])
            self.assertEqual('2.1.303', value['claude_code_version'])
            self.assertEqual(200, client.get(path + '/file?path=capture_index.json').status_code)
            self.assertEqual(404, client.get(path + '/file?path=../../secret').status_code)
            self.assertEqual(404, client.get(path + '/file?path=http_capture.jsonl').status_code)
            self.assertEqual(404, client.get(prefix + '/work/missing/capture').status_code)


if __name__ == '__main__':
    unittest.main()
