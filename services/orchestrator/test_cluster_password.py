"""节点密码认证的只写合同、兼容及私有文件验证。"""
from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from cluster_api import cluster_router
from cluster_nodes import NodeConfiguration, NodeCreate
from cluster_ssh import SshNode
import test_cluster_nodes as node_fixture


class ClusterPasswordTests(unittest.TestCase):
    """复用真实 SQLite 夹具验证密码材料的边界。"""

    def setUp(self) -> None:
        """准备独立节点存储与合成密码。:return: None。"""
        self.fixture = node_fixture.ClusterNodeTests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.password = ' 合成密碼 $`!;\\" 密码尾空格 '
        self.request = NodeCreate(**self.fixture.config, auth_method='password', password=self.password)

    def test_password_is_write_only_and_registration_failure_cleans_its_own_files(self) -> None:
        """秘密仅进入私有文件，重复登记清理本次材料。:return: None。"""
        result = self.fixture.service.register(self.request)
        self.assertEqual('password', result['auth_method'])
        self.assertNotIn('password', result)
        self.assertNotIn(self.password, self.request.model_dump_json() + repr(self.request))
        self.assertNotIn(self.password, json.dumps(self.fixture.store.list(), ensure_ascii=False))
        connection = self.fixture.database()
        self.addCleanup(connection.close)
        self.assertNotIn(self.password, json.dumps([tuple(row) for row in connection.execute('SELECT * FROM cluster_nodes')]))
        private = self.fixture.root / 'cluster-private' / result['node_key']
        self.assertEqual(self.password + '\n', (private / 'password').read_text())
        self.assertEqual(0o700, private.stat().st_mode & 0o777)
        self.assertEqual(0o600, (private / 'password').stat().st_mode & 0o777)
        self.assertFalse((private / 'identity').exists())
        with self.assertRaisesRegex(ValueError, '已登记'):
            self.fixture.service.register(self.request)
        self.assertEqual([private], list(private.parent.iterdir()))

    def test_old_configuration_and_requests_default_to_private_key(self) -> None:
        """旧节点 JSON 和私钥请求保持默认认证。:return: None。"""
        self.assertEqual('private_key', NodeConfiguration(**self.fixture.config).auth_method)
        request = NodeCreate(**self.fixture.config, private_key=self.fixture.key.read_text())
        self.assertEqual('private_key', request.auth_method)
        self.assertNotIn('PRIVATE KEY', repr(request))
        node = self.fixture.service.register(request)
        connection = self.fixture.database()
        self.addCleanup(connection.close)
        stored = json.loads(connection.execute('SELECT config_json FROM cluster_nodes WHERE id=?',
            (node['id'],)).fetchone()[0])
        self.assertNotIn('auth_method', stored)
        self.assertEqual(set(self.fixture.config) | {'enabled'}, set(stored))
        with connection:
            connection.execute('UPDATE cluster_nodes SET config_json=? WHERE id=?',
                (json.dumps(self.fixture.config), node['id']))
        self.assertEqual('private_key', self.fixture.store.list()[1]['auth_method'])
        self.assertIsNone(self.fixture.store.list()[0]['auth_method'])

    def test_invalid_credentials_are_rejected_without_echoing_request(self) -> None:
        """冲突、空值和控制字符均返回固定错误。:return: None。"""
        app = FastAPI()
        app.include_router(cluster_router(lambda: self.fixture.service))
        cases = [{'auth_method': 'password'}, {'auth_method': 'password', 'password': ''},
            {'password': self.password}, {'auth_method': 'unknown', 'password': self.password},
            {'auth_method': 'password', 'password': self.password, 'private_key': self.fixture.key.read_text()}]
        cases.extend({'auth_method': 'password', 'password': value}
            for value in ('secret\x00', 'secret\n', 'secret\r', 'x' * 4097, 123))
        with TestClient(app) as client:
            for values in cases:
                with self.subTest(fields=list(values)):
                    with self.assertRaises(ValidationError):
                        NodeCreate(**self.fixture.config, **values)
                    response = client.post('/api/nodes', json={**self.fixture.config, **values})
                    self.assertEqual(422, response.status_code)
                    self.assertNotIn(self.password, response.text)
                    self.assertNotIn('PRIVATE KEY', response.text)

    def test_reloaded_password_uses_a_private_descriptor_and_rejects_unsafe_files(self) -> None:
        """重启后的凭据由无链接文件描述符传递，公开权限与链接被拒绝。:return: None。"""
        result = self.fixture.service.register(self.request)
        node = SshNode(result['node_key'], NodeConfiguration.model_validate(self.request.model_dump()),
            self.fixture.root / 'cluster-private', self.fixture.root / 'transport')
        descriptor = node._password_descriptor()
        try:
            arguments = node._arguments(password_descriptor=descriptor)
            self.assertEqual(['sshpass', '-d', str(descriptor)], arguments[:3])
            self.assertNotIn(self.password, ' '.join(arguments))
            self.assertEqual((self.password + '\n').encode(), os.read(descriptor, 16385))
            self.assertIn('PreferredAuthentications=password', arguments)
            self.assertIn('StrictHostKeyChecking=yes', arguments)
        finally:
            os.close(descriptor)
        path = node.private / 'password'
        path.chmod(0o644)
        with self.assertRaisesRegex(ValueError, '权限'):
            node._password_descriptor()
        path.chmod(0o600)
        original = path.with_name('saved-password')
        path.rename(original)
        path.symlink_to(original)
        with self.assertRaises(OSError):
            node._password_descriptor()

    def test_missing_installation_configuration_names_the_exact_variable(self) -> None:
        """旧模板缺配置时返回配置名，安装保持原始状态。:return: None。"""
        node = self.fixture.service.register(self.request)
        app = FastAPI()
        app.include_router(cluster_router(lambda: self.fixture.service))
        with patch.dict(os.environ, {'V3_DEPLOYMENT_ID': 'synthetic', 'V3_RELEASE': 'synthetic',
                'V3_ACCOUNT_IMAGE': 'synthetic-private-value'}, clear=True), TestClient(app) as client:
            response = client.post(f"/api/nodes/{node['id']}/prepare", json={'revision': node['revision']})
        self.assertEqual(409, response.status_code)
        self.assertIn('V3_CONTROL_IMAGE', response.json()['detail'])
        self.assertNotIn('synthetic-private-value', response.text)
        self.assertIsNone(self.fixture.store.list()[1]['preparation'])


if __name__ == '__main__':
    unittest.main()
