"""验证代理引用摘要、跨域去重及未知草稿保护。"""
import sqlite3
import unittest
from unittest.mock import Mock
from proxy_references import collect_references, connection_fingerprint


class ProxyReferenceTests(unittest.TestCase):
    """仅使用合成内存数据库与私有配置回执。"""

    def test_fingerprint_and_reference_completeness(self):
        """已绑定账号排除，未知草稿保留完整性失败。@return None。"""
        db = sqlite3.connect(':memory:')
        db.row_factory = sqlite3.Row
        self.addCleanup(db.close)
        db.execute('CREATE TABLE accounts(id INTEGER,name TEXT,enabled INTEGER,upstream_proxy_scheme TEXT,'
            'upstream_socks5_host TEXT,upstream_socks5_port INTEGER,upstream_socks5_user TEXT,'
            'upstream_socks5_pass TEXT,deleted_at TEXT,cc2api_account_id INTEGER)')
        db.executemany('INSERT INTO accounts VALUES(?,?,?,?,?,?,?,?,NULL,?)', [
            (1, '独立任务', 1, 'http', 'proxy.test', 8080, 'user', 'secret', None),
            (2, '已绑定', 1, 'http', 'proxy.test', 8080, 'user', 'secret', 7)])
        # 工厂返回可关闭包装，保持本测试共享内存库。
        wrapper = Mock(wraps=db)
        wrapper.close = Mock()
        drafts = Mock()
        drafts.rows.return_value = [{'environment_id': 'draft', 'name': '未提交'}]
        drafts.account.side_effect = ValueError('准备中')
        result = collect_references(lambda: wrapper, drafts)
        self.assertFalse(result['complete'])
        self.assertEqual([value['id'] for value in result['references']], ['1'])
        self.assertNotIn('secret', str(result))
        account = dict(db.execute('SELECT * FROM accounts WHERE id=1').fetchone())
        self.assertEqual(len(connection_fingerprint(account)), 64)
        account['upstream_socks5_host'] = ''
        self.assertIsNone(connection_fingerprint(account))
        self.assertTrue(collect_references(lambda: wrapper, None)['complete'])
