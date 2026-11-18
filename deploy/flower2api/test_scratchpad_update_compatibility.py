"""使用实际签名与更新入口验证临时文件布局的跨版本保护。"""
import copy
import json
import unittest
import uuid
from unittest.mock import Mock, patch

from system_release import create_index, create_release, sign_file
from system_update_contract import compatible_scratchpad, validate_release
from system_update_host import HostDeployment
import test_system_updater as updater_tests


class ScratchpadUpdateCompatibilityTests(unittest.TestCase):
    """合成密钥及隔离文件验证兼容阶段、激活阶段和旧版拒绝。"""

    def setUp(self) -> None:
        """复用真实更新器夹具及其独立资源清理。:return: None。"""
        self.case = updater_tests.SystemUpdaterTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        case = self.case
        case.old = self._signed(case.old, {**case.old['compatibility'], 'scratchpad_storage': 1})
        case.engine.state['current']['release'] = case.old
        case.target = self._signed(case.target, {**case.target['compatibility'], 'scratchpad_storage': 1})
        self._catalog()

    def _signed(self, release: dict, capabilities: dict, *, changed_account: bool = False) -> dict:
        value = copy.deepcopy(release)
        value['compatibility'] = capabilities
        if changed_account:
            value['account']['content_sha256'] = 'e' * 64
        folder = self.case.root / 'releases' / value['release']
        path = folder / 'system-release.json'
        path.write_text(json.dumps(value))
        path.with_suffix('.sig').unlink()
        sign_file(path, self.case.fixture.key)
        return value

    def _catalog(self) -> None:
        source = self.case.root / 'releases' / self.case.target['release'] / 'system-release.json'
        self.case.engine.state['catalog'] = create_index(source, None,
            self.case.fixture.root / ('catalog-' + uuid.uuid4().hex + '.json'), self.case.fixture.key)

    def test_capability_matrix_and_strict_protocol_types(self) -> None:
        """历史、兼容和激活版本按实际能力判断，非法声明拒绝。:return: None。"""
        bridge = copy.deepcopy(self.case.old)
        legacy = copy.deepcopy(bridge)
        legacy['compatibility'].pop('scratchpad_storage')
        active = copy.deepcopy(bridge)
        active['compatibility']['scratchpad_activation'] = 1
        for source, target, expected in ((legacy, bridge, True), (legacy, active, False),
                (bridge, active, True), (active, bridge, True), (active, legacy, False)):
            with self.subTest(source=source['compatibility'], target=target['compatibility']):
                self.assertEqual(expected, compatible_scratchpad(source, target))
        self.assertEqual(validate_release(legacy), legacy)
        for name in ('scratchpad_storage', 'scratchpad_activation'):
            for invalid in (True, 0, 2, '1'):
                value = copy.deepcopy(active)
                value['compatibility'][name] = invalid
                with self.subTest(name=name, invalid=invalid), self.assertRaises(ValueError):
                    validate_release(value)
        active['compatibility'].pop('scratchpad_storage')
        with self.assertRaisesRegex(ValueError, '缺少恢复能力'):
            validate_release(active)

    def test_signed_activation_requires_bridge_before_any_host_work(self) -> None:
        """跳过兼容阶段的实际签名目标在宿主动作前拒绝。:return: None。"""
        case = self.case
        legacy = copy.deepcopy(case.old['compatibility'])
        legacy.pop('scratchpad_storage')
        case.engine.state['current']['release'] = self._signed(case.old, legacy)
        active = {**case.target['compatibility'], 'scratchpad_activation': 1}
        case.target = self._signed(case.target, active, changed_account=True)
        self._catalog()
        self.assertFalse(case.engine.releases()['releases'][0]['data_compatible'])
        for action in ('prepare', 'install'):
            with self.subTest(action=action), self.assertRaisesRegex(ValueError, '临时文件布局不兼容'):
                case.engine.submit(action, case.request())
        self.assertEqual([], case.backend.calls)
        self.assertEqual([], list((case.root / 'operations').iterdir()))

    def test_legacy_rollback_and_install_bypass_are_both_rejected(self) -> None:
        """回退展示与两种实际切换入口共同拒绝旧布局接管。:return: None。"""
        case = self.case
        legacy = copy.deepcopy(case.target['compatibility'])
        legacy.pop('scratchpad_storage')
        case.target = self._signed(case.target, legacy)
        self._catalog()
        case.engine.state['history'] = [{'release': case.target,
            'selection': {role: case.target[role] for role in ('control', 'account')}}]
        self.assertFalse(case.engine.status()['history'][0]['rollback_available'])
        self.assertFalse(case.engine.releases()['releases'][0]['data_compatible'])
        for action in ('rollback', 'install'):
            with self.subTest(action=action), self.assertRaisesRegex(ValueError, '临时文件布局不兼容'):
                case.engine.submit(action, case.request())
        self.assertEqual([], case.backend.calls)

    def test_activation_health_failure_restores_compatible_bridge(self) -> None:
        """激活验收失败沿原状态机回到具有恢复能力的兼容版本。:return: None。"""
        case = self.case
        active = {**case.target['compatibility'], 'scratchpad_activation': 1}
        case.target = self._signed(case.target, active, changed_account=True)
        self._catalog()
        case.backend.fail = 'health'
        case.engine.submit('install', case.request())
        state = case.join()
        self.assertEqual('restored', state['operation']['phase'])
        self.assertEqual(case.old['release'], state['current_release'])
        self.assertEqual(1, case.engine.state['current']['release']['compatibility']['scratchpad_storage'])
        self.assertIn('restore', case.backend.calls)
        self.assertFalse(case.backend.blocked)

    def test_host_blocks_incompatible_partial_restore_before_control_changes(self) -> None:
        """异常旧操作的宿主恢复先保留门禁，再拒绝旧程序接管。:return: None。"""
        case = self.case
        legacy = copy.deepcopy(case.old)
        legacy['compatibility'].pop('scratchpad_storage')
        host = HostDeployment.__new__(HostDeployment)
        host.root, host.gate = case.root, case.root / 'gate'
        host.policy = {'deployment': 'test'}
        host.block = Mock()
        host.verify_images = Mock()
        host.controls = Mock()
        operation = {'operation_id': str(uuid.uuid4()), 'original': {'release': legacy},
            'selected': {'release': case.target}, 'environment_intents': {'a' * 32: {}}}
        with patch('system_update_host.read_gate', return_value={'phase': 'blocked'}), \
                self.assertRaisesRegex(ValueError, '保留维护现场'):
            host.restore(operation, Mock())
        host.block.assert_called_once_with(operation)
        host.verify_images.assert_not_called()
        host.controls.assert_not_called()

    def test_publisher_derives_activation_from_account_build_metadata(self) -> None:
        """真实签名发布根据构建记录声明激活，非法构建字段拒绝。:return: None。"""
        fixture = self.case.fixture
        fixture.build['images']['control']['cli_scratchpad_storage'] = 1
        fixture.build['images']['account']['cli_scratchpad_protocol'] = 1
        fixture.manifest.write_text(json.dumps(fixture.build))
        value = create_release(fixture.manifest, fixture.policy, fixture.root / 'active-release',
            fixture.key, [12, 1], '启用临时文件磁盘布局')
        self.assertEqual(1, value['compatibility']['scratchpad_storage'])
        self.assertEqual(1, value['compatibility']['scratchpad_activation'])
        for invalid in (True, 2, '1'):
            fixture.build['images']['account']['cli_scratchpad_protocol'] = invalid
            fixture.manifest.write_text(json.dumps(fixture.build))
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, '镜像能力声明无效'):
                create_release(fixture.manifest, fixture.policy, fixture.root / 'invalid-release',
                    fixture.key, [13, 1], '非法声明')


if __name__ == '__main__':
    unittest.main()
