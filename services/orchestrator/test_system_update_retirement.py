"""历史回退前由当前所有者受证收口角色的真实 HTTP 合同。"""
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from system_updates import system_updates_router


class RetirementTests(unittest.TestCase):
    """核对门禁、代次和排空后才允许移除，身份及重建由原生命周期负责。"""

    def test_retirement_requires_proof_idle_and_exact_generation(self) -> None:
        """授权成功只收口角色；错误证明、代次及在途分别拒绝。@return None。"""
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'bench.sqlite'
            with sqlite3.connect(database) as connection:
                connection.executescript('CREATE TABLE account_environments(environment_id TEXT,account_id INTEGER,generation INTEGER,state TEXT);'
                    "INSERT INTO account_environments VALUES('synthetic',1,7,'ready');"
                    'CREATE TABLE accounts(id INTEGER);INSERT INTO accounts VALUES(1);')

            def connect():
                """打开独立真实 SQLite 连接。@return 带列名的连接。"""
                connection = sqlite3.connect(database)
                connection.row_factory = sqlite3.Row
                return connection

            runtime = SimpleNamespace(database=connect, environment_lock=lambda identifier: threading.RLock(),
                _stop_environment=Mock(), _update=lambda row, **fields: row.update(fields), ensure=Mock())
            evidence = {'ready': True, 'active': 0, 'environments': []}
            gate = {'phase': 'blocked', 'operation_id': 'synthetic-operation', 'epoch': 'synthetic-epoch'}
            with patch('system_updates.UPDATE_GATE', SimpleNamespace(state=lambda: gate)), \
                    patch('system_updates.update_token', return_value='synthetic-token'), \
                    patch('system_updates.runtime_snapshot', return_value=evidence), \
                    patch('system_updates.partial_restore_ready') as partial, \
                    patch('system_updates.image_origin', return_value={'release': 'ci-2-1'}):
                app = FastAPI()
                app.include_router(system_updates_router(lambda: runtime))
                with TestClient(app) as client:
                    body = {'operation_id': gate['operation_id'], 'epoch': gate['epoch'],
                        'environment_id': 'synthetic', 'generation': 7, 'action': 'retire',
                        'allowed_image_ids': ['sha256:' + 'a' * 64]}
                    headers = {'x-v3-update-token': 'synthetic-token'}
                    self.assertEqual(client.post('/internal/v3/system-updates/environment', json=body).status_code, 403)
                    for changes in ({'epoch': 'foreign'}, {'generation': 8}):
                        self.assertEqual(client.post('/internal/v3/system-updates/environment', headers=headers,
                            json={**body, **changes}).status_code, 409)
                    evidence.update(ready=False, active=1)
                    self.assertEqual(client.post('/internal/v3/system-updates/environment', headers=headers, json=body).status_code, 409)
                    runtime._stop_environment.assert_not_called()
                    evidence.update(ready=True, active=0)
                    partial.side_effect = ValueError('合成角色来源冲突')
                    self.assertEqual(client.post('/internal/v3/system-updates/environment', headers=headers, json=body).status_code, 409)
                    runtime._stop_environment.assert_not_called()
                    partial.side_effect = None
                    evidence.update(ready=False, environments=[{'environment_id': 'sibling', 'blockers': ['合成待恢复角色']}])
                    response = client.post('/internal/v3/system-updates/environment', headers=headers, json=body)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json()['generation'], 7)
                    self.assertEqual(response.json()['state'], 'stopped')
                    self.assertIsNone(response.json()['origin'])
                    self.assertTrue(runtime._stop_environment.call_args.kwargs['remove'])
                    self.assertEqual(partial.call_args.args[-1], body['allowed_image_ids'])
                    runtime.ensure.assert_not_called()
