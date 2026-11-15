"""使用中代理同步的锁序、幂等、身份转换和失败恢复验证。"""
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock

from proxy_references import connection_fingerprint
from proxy_sync import synchronize_proxy


class ProxySyncTests(unittest.TestCase):
    """合成数据库与本地配置，验证真实持久写入边界。"""

    def setUp(self):
        """准备独立任务和可切换草稿。@return None。"""
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        path = Path(self.directory.name) / 'data.db'
        def database():
            connection = sqlite3.connect(path)
            connection.row_factory = sqlite3.Row
            return connection
        self.database = database
        with database() as connection:
            connection.execute('CREATE TABLE accounts(id INTEGER PRIMARY KEY,name TEXT,enabled INTEGER,'
                'upstream_proxy_scheme TEXT,upstream_socks5_host TEXT,upstream_socks5_port INTEGER,'
                'upstream_socks5_user TEXT,upstream_socks5_pass TEXT,cc2api_account_id INTEGER,deleted_at TEXT)')
            connection.execute("INSERT INTO accounts VALUES(1,'task',1,'http','old.test',8080,'u','p',NULL,NULL)")
            connection.execute('CREATE TABLE account_environments(environment_id TEXT,account_id INTEGER,name TEXT)')
            connection.execute("INSERT INTO account_environments VALUES('env',1,'task')")
            account = dict(connection.execute('SELECT * FROM accounts').fetchone())
        self.body = {'target': {'kind': 'task', 'id': '1'}, 'source': connection_fingerprint(account),
            'destination': 'socks5://new:secret@new.test:1080'}
        self.owner, self.profile, self.environment = threading.Lock(), threading.Lock(), threading.RLock()
        self.runtime = Mock(lock=threading.Lock())
        self.runtime.environment_lock.return_value = self.environment
        self.runtime.environment_jobs.return_value = []
        self.runtime._running_sender_active.return_value = False
        self.drafts = Mock()
        self.active = Mock(return_value=False)
        self.account = account

    def sync(self):
        """调用真实同步逻辑。@return 同步回执。"""
        return synchronize_proxy(self.body, self.database, threading.Lock(), self.runtime,
            self.drafts, lambda _: self.owner, lambda _: self.profile, self.active)

    def test_busy_retries_and_success_is_idempotent(self):
        """繁忙保持旧连接；成功保留其它字段并可重复确认。@return None。"""
        self.runtime.environment_jobs.return_value = ['job']
        self.assertFalse(self.sync()['complete'])
        self.runtime._stop_environment.assert_not_called()
        self.runtime.environment_jobs.return_value = []
        self.assertTrue(self.sync()['complete'])
        self.runtime._stop_environment.assert_called_once()
        self.assertTrue(self.sync()['complete'])
        self.runtime._stop_environment.assert_called_once()
        with self.database() as connection:
            row = dict(connection.execute('SELECT * FROM accounts').fetchone())
        self.assertEqual((row['upstream_proxy_scheme'], row['upstream_socks5_host'], row['enabled']), ('socks5', 'new.test', 1))

    def test_owner_login_and_stop_failure_preserve_connection(self):
        """维护锁、活跃授权和停止失败均保留待重试配置。@return None。"""
        with self.owner:
            self.assertFalse(self.sync()['complete'])
        self.active.return_value = True
        self.assertFalse(self.sync()['complete'])
        self.active.return_value = False
        self.runtime._stop_environment.side_effect = RuntimeError('模拟停止失败')
        with self.assertRaises(RuntimeError):
            self.sync()
        with self.database() as connection:
            self.assertEqual(connection.execute('SELECT upstream_socks5_host FROM accounts').fetchone()[0], 'old.test')

    def test_new_user_choice_and_binding_are_respected(self):
        """手动选线先于队列重试时不被旧任务覆盖；绑定后转交网关。@return None。"""
        with self.database() as connection:
            connection.execute("UPDATE accounts SET upstream_socks5_host='manual.test'")
        self.assertTrue(self.sync()['complete'])
        self.runtime._stop_environment.assert_not_called()
        with self.database() as connection:
            connection.execute('UPDATE accounts SET cc2api_account_id=8')
        self.assertEqual(self.sync(), {'complete': False, 'gateway_account_id': 8})

    def test_draft_keeps_secrets_and_can_transfer_identity(self):
        """草稿仅变更原代理配置，已提交身份继续流转到任务账号。@return None。"""
        self.body['target'] = {'kind': 'draft', 'id': 'a' * 32}
        self.drafts.row.return_value = {'environment_id': 'a' * 32, 'account_id': None, 'name': 'draft'}
        self.drafts.account.return_value = self.account
        config = Path(self.directory.name) / 'sender.json'
        config.write_text(json.dumps({'proxy_source': 'http://u:p@old.test:8080', 'binding': {'secret': 'retained'}}))
        self.runtime._sender_config.return_value = config
        result = self.sync()
        self.assertEqual(result, {'complete': True})
        saved = self.runtime._write_sender_config.call_args.args[1]
        self.assertEqual(saved['binding'], {'secret': 'retained'})
        self.assertEqual(saved['proxy_source'], self.body['destination'])
        self.drafts.row.return_value['account_id'] = 1
        self.assertEqual(self.sync(), {'complete': False, 'task_account_id': 1})


if __name__ == '__main__':
    unittest.main()
