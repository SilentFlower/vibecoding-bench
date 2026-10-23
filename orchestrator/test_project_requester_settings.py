"""页面配置、私有持久化、多模型优先级与动态切换的回归。"""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

import main
from project_requester_settings import ProjectRequesterSettings
from test_project_dialogue import _http_error, _response


class RequesterSettingsTests(unittest.TestCase):
    """设置落在私有文件中，接口和调用元数据不包含密钥。"""

    def setUp(self) -> None:
        """准备隔离配置根和合成密钥。@return None。"""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'settings/project-requester.json'
        self.environment = {'PROJECT_REQUESTER_BASE_URL': 'https://initial.example/v1',
            'PROJECT_REQUESTER_API_KEY': 'isolated-private-key', 'PROJECT_REQUESTER_MODEL': 'primary',
            'PROJECT_REQUESTER_FALLBACK_MODEL': 'secondary'}
        self.store = ProjectRequesterSettings(self.path, self.environment)

    def test_save_restart_blank_key_and_restore_environment(self) -> None:
        """保存后重启保留，空密钥沿用，恢复环境不修改旧客户端。@return None。"""
        initial = self.store.client()
        client = self.store.save('https://changed.example/v1', ['new-primary', 'new-secondary', 'third'])
        self.assertEqual(('new-primary', 'new-secondary', 'third'), client.models)
        self.assertEqual(0o600, self.path.stat().st_mode & 0o777)
        self.assertEqual(0o700, self.path.parent.stat().st_mode & 0o777)
        restored = ProjectRequesterSettings(self.path, self.environment)
        self.assertEqual(client.revision, restored.client().revision)
        self.assertTrue(restored.public()['api_key_configured'])
        self.assertNotIn(self.environment['PROJECT_REQUESTER_API_KEY'], json.dumps(restored.public()))
        self.assertNotIn('api_key', restored.public())
        replacement = restored.save('https://other.example/v1', ['only'], '')
        self.assertNotEqual(client.revision, replacement.revision)
        self.assertEqual('https://changed.example/v1', client.base_url)
        self.assertEqual('https://initial.example/v1', initial.base_url)
        self.assertEqual(('primary', 'secondary'), restored.reset().models)
        self.assertFalse(self.path.exists())

    def test_invalid_updates_do_not_replace_valid_settings_or_echo_secret(self) -> None:
        """非法地址、重复模型、过量模型和混入密钥的字段不改变现配置。@return None。"""
        self.store.save('https://valid.example/v1', ['first', 'second'])
        before = self.path.read_bytes()
        for url, models in [('http://invalid.example', ['one']), ('https://user:password@invalid.example', ['one']),
                ('https://valid.example/v1', ['one', 'one']), ('https://valid.example/v1', []),
                ('https://valid.example/v1', [str(number) for number in range(9)]),
                ('https://valid.example/v1', [self.environment['PROJECT_REQUESTER_API_KEY']])]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.store.save(url, models)
            self.assertEqual(before, self.path.read_bytes())

    def test_all_models_are_attempted_once_in_order_and_configuration_is_recorded(self) -> None:
        """主备均暂时失败时依次使用第三模型，记录本轮真实配置来源。@return None。"""
        client = self.store.save('https://models.example/v1', ['first', 'second', 'third'])
        opener = Mock()
        opener.open.side_effect = [_http_error(402), _http_error(503), _response()]
        client._opener = opener
        result = client.generate({'goal': 'Isolated protocol fixture.'})
        self.assertEqual(('ready', 'third'), (result['status'], result['model']))
        self.assertEqual(['first', 'second', 'third'], [json.loads(call.args[0].data)['model'] for call in opener.open.call_args_list])
        self.assertEqual(client.revision, result['configuration_revision'])
        self.assertEqual('https://models.example/v1', result['provider_base_url'])
        self.assertNotIn(self.environment['PROJECT_REQUESTER_API_KEY'], json.dumps(result))

    def test_corrupt_saved_configuration_does_not_silently_use_environment(self) -> None:
        """坏文件保留故障，重新填写完整密钥可恢复，不能悄悄切换供应商。@return None。"""
        self.path.parent.mkdir()
        self.path.write_text('invalid-json')
        self.assertIsNone(self.store.client())
        self.assertEqual('invalid', self.store.public()['source'])
        self.store.save('https://repaired.example/v1', ['one'], 'new-private-key')
        self.assertTrue(self.store.public()['ready'])

    def test_management_api_masks_key_and_applies_dynamic_clients(self) -> None:
        """真实 API 保存、读取及恢复都只返回脱敏结果，后续任务获得新客户端。@return None。"""
        owner = SimpleNamespace(dialogue=self.store.client())
        with patch.multiple(main, project_requester_settings=self.store, project_iterations=owner,
                _AUTH_ENABLED=False, V3_ENABLED=False):
            # 不进入 lifespan，接口回归只能访问本次合成配置，不能启动后台调度器。
            api = TestClient(main.app)
            self.addCleanup(api.close)
            response = api.put('/api/settings/project-requester', json={'base_url': 'https://updated.example/v1',
                'models': ['first', 'second', 'third'], 'api_key': 'replacement-private-key'})
            self.assertEqual(200, response.status_code)
            self.assertNotIn('replacement-private-key', response.text)
            self.assertEqual(('first', 'second', 'third'), owner.dialogue.models)
            original_client = owner.dialogue
            response = api.put('/api/settings/project-requester', json={'base_url': 'https://next.example/v1', 'models': ['next']})
            self.assertEqual(200, response.status_code)
            self.assertEqual('https://updated.example/v1', original_client.base_url)
            self.assertEqual('https://next.example/v1', owner.dialogue.base_url)
            self.assertEqual(['next'], api.get('/api/settings/project-requester').json()['models'])
            self.assertEqual(200, api.delete('/api/settings/project-requester').status_code)
            self.assertEqual(('primary', 'secondary'), owner.dialogue.models)

    def test_validation_errors_and_unauthenticated_calls_never_echo_private_input(self) -> None:
        """DTO 失败不回显密钥，未登录请求不能读写配置。@return None。"""
        with patch.multiple(main, project_requester_settings=self.store, _AUTH_ENABLED=False, V3_ENABLED=False):
            api = TestClient(main.app)
            self.addCleanup(api.close)
            response = api.put('/api/settings/project-requester', json={'base_url': 'https://example.test',
                'models': ['one'], 'api_key': ['private-validation-sentinel']})
            self.assertEqual(422, response.status_code)
            self.assertNotIn('private-validation-sentinel', response.text)
            with patch.object(main, '_AUTH_ENABLED', True):
                self.assertEqual(401, api.get('/api/settings/project-requester').status_code)
                self.assertEqual(401, api.delete('/api/settings/project-requester').status_code)

    def test_failed_save_preserves_previous_configuration_and_client(self) -> None:
        """磁盘保存失败时不热切换客户端，也不丢失原密钥。@return None。"""
        original = self.store.save('https://before.example/v1', ['before'])
        before = self.path.read_bytes()
        owner = SimpleNamespace(dialogue=original)
        with patch.multiple(main, project_requester_settings=self.store, project_iterations=owner,
                _AUTH_ENABLED=False, V3_ENABLED=False), patch('project_requester_settings.write_document', side_effect=OSError('private-disk-error')):
            api = TestClient(main.app)
            self.addCleanup(api.close)
            response = api.put('/api/settings/project-requester', json={'base_url': 'https://after.example/v1',
                'models': ['after'], 'api_key': 'new-private-key'})
            self.assertEqual(500, response.status_code)
            self.assertNotIn('private-disk-error', response.text)
            self.assertIs(owner.dialogue, original)
            self.assertEqual(before, self.path.read_bytes())


if __name__ == '__main__':
    unittest.main()
