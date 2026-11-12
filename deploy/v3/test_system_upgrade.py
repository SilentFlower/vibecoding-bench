"""固定底座接入的真实文件、签名、归属检查与失败恢复。"""
import hashlib
import json
import os
from unittest.mock import patch
import unittest
from pathlib import Path
from source_layout import source_path

from install_system_updater import REPO, SOURCE_FILES
from runtime_files import atomic_json, atomic_text
from system_update_gate import read_gate
from upgrade_system_updater import recover_upgrade, upgrade
import upgrade_system_updater as upgrade_module
import test_system_updater as updater_tests


class UpdaterUpgradeTests(unittest.TestCase):
    """服务边界注入，真实执行来源、锁、私有文件及恢复操作。"""

    def setUp(self) -> None:
        """建立有效的 v1 安装和固定源码。@return None。"""
        base = updater_tests.SystemUpdaterTests()
        base.setUp()
        self.addCleanup(base.doCleanups)
        self.root, self.fixture = base.root, base.fixture
        self.policy = base.policy
        atomic_json(self.root / 'policy.json', self.policy)
        for name in SOURCE_FILES:
            atomic_text(self.root / 'source' / name, (source_path(REPO, name)).read_text())
        marker = self.root / 'source/deploy/v3/system_updater.py'
        atomic_text(marker, marker.read_text() + '\n# 合成旧安装标记，用于验证精确恢复。\n')
        self.before = {name: (self.root / 'source' / name).read_bytes() for name in SOURCE_FILES}
        state = json.loads((self.root / 'state.json').read_text())
        self.state = state
        atomic_json(self.root / 'gate/admission.json', {'schema_version': 1, 'deployment': 'test',
            'operation_id': None, 'epoch': '00000000-0000-0000-0000-000000000001', 'phase': 'idle',
            'target_release': None, 'revision': state['revision'], 'created_at': '2026-11-11T00:00:00Z'})
        unit = f'[Service]\nExecStart=/usr/bin/python3 {self.root}/source/deploy/v3/system_updater.py --policy {self.root}/policy.json\n'
        atomic_text(self.root / 'vibebench-updater.service', unit)
        self.fragment = self.fixture.root / 'synthetic-updater.service'
        atomic_text(self.fragment, unit)
        self.calls = []
        self.active = True
        self.fail_start = False

    def control(self, *arguments) -> str:
        """模拟已核验 systemd 服务，仅记录固定动作。:param arguments: 参数。@return 服务事实。"""
        self.calls.append(arguments)
        if arguments[0] == 'show':
            return str(self.fragment)
        if arguments[0] == 'is-active':
            return 'active' if self.active else 'inactive'
        if arguments[0] == 'stop':
            self.active = False
        if arguments[0] == 'start':
            if self.fail_start:
                self.fail_start = False
                raise RuntimeError('synthetic-start-failure')
            self.active = True
        return ''

    def probe(self, root) -> dict:
        """返回新服务公开事实。:param root: 独立安装根。@return 合成接口状态。"""
        return {'migration_capability': True, 'deployment': 'test', 'revision': self.state['revision'],
            'current_release': self.state['current']['release']['release']}

    def apply(self, enabled=True, probe=None) -> dict:
        """执行同一精确接入入口。:param enabled: 是否应用。:param probe: 接口边界。@return 结果。"""
        return upgrade(self.root / 'policy.json', REPO, 'synthetic-updater.service', apply=enabled,
            control=self.control, probe=probe or self.probe)

    def test_preview_keeps_current_files_and_state(self) -> None:
        """默认预览列出精确摘要且保持安装状态。@return None。"""
        value = self.apply(False)
        self.assertEqual(value['status'], 'planned')
        self.assertEqual({entry['path'] for entry in value['files']}, set(SOURCE_FILES))
        self.assertEqual(json.loads((self.root / 'state.json').read_text()), self.state)
        self.assertFalse(any(args[0] == 'stop' for args in self.calls))

    def test_upgrade_preserves_installation_and_switches_capability(self) -> None:
        """升级源码和通道能力，当前安装、历史和代次保持。@return None。"""
        self.assertEqual(self.apply()['status'], 'upgraded')
        state = json.loads((self.root / 'state.json').read_text())
        for key in ('current', 'history', 'revision', 'active_operation'):
            self.assertEqual(state[key], self.state[key])
        self.assertEqual(json.loads((self.root / 'policy.json').read_text())['schema_version'], 2)
        self.assertEqual(state['catalog'], {})
        for name in SOURCE_FILES:
            self.assertEqual((self.root / 'source' / name).read_bytes(), (source_path(REPO, name)).read_bytes())
        self.assertTrue(self.active)

    def test_failed_start_restores_exact_sources_and_policy(self) -> None:
        """新服务启动失败恢复旧文件、策略及原目录。@return None。"""
        self.fail_start = True
        with self.assertRaisesRegex(RuntimeError, 'synthetic-start-failure'):
            self.apply()
        self.assertEqual(json.loads((self.root / 'state.json').read_text()), self.state)
        self.assertEqual(json.loads((self.root / 'policy.json').read_text()), self.policy)
        for name, raw in self.before.items():
            self.assertEqual((self.root / 'source' / name).read_bytes(), raw)
        self.assertTrue(self.active)

    def test_wrong_service_or_active_operation_rejected(self) -> None:
        """外来服务及在途更新不能被接入覆盖。@return None。"""
        atomic_text(self.fragment, '[Service]\nExecStart=/usr/bin/other-service\n')
        with self.assertRaisesRegex(ValueError, '归属'):
            self.apply(False)
        atomic_json(self.root / 'state.json', {**self.state, 'active_operation': 'later-operation'})
        with self.assertRaisesRegex(ValueError, '原更新'):
            self.apply()
        self.assertFalse(any(args[0] == 'stop' for args in self.calls))

    def test_wrong_capability_rolls_back_before_success(self) -> None:
        """systemd active 不能代替真实 socket 能力验收。@return None。"""
        with self.assertRaisesRegex(ValueError, '能力'):
            self.apply(probe=lambda root: {**self.probe(root), 'migration_capability': False})
        self.assertEqual(json.loads((self.root / 'policy.json').read_text()), self.policy)
        self.assertTrue(self.active)


    def _file_control(self, *arguments) -> str:
        self.calls.append(arguments)
        path = self.root / 'synthetic-service.json'
        if arguments[0] == 'show':
            return str(self.fragment)
        if arguments[0] == 'is-active':
            return 'active' if json.loads(path.read_text())['active'] else 'inactive'
        if arguments[0] in ('start', 'stop'):
            atomic_json(path, {'active': arguments[0] == 'start'})
        return ''

    def _interrupt_upgrade(self, point: str) -> str:
        atomic_json(self.root / 'synthetic-service.json', {'active': True})
        target = self.root / {'source': 'source/deploy/v3/system_updater.py',
            'policy': 'policy.json', 'state': 'state.json'}[point]
        pid = os.fork()
        if pid == 0:
            def write_text(path, value, *args, **kwargs):
                atomic_text(path, value, *args, **kwargs)
                if path == target:
                    os._exit(93)

            def write_json(path, value, *args, **kwargs):
                atomic_json(path, value, *args, **kwargs)
                if path == target:
                    os._exit(93)

            with patch.object(upgrade_module, 'atomic_text', write_text), patch.object(upgrade_module, 'atomic_json', write_json):
                upgrade(self.root / 'policy.json', REPO, 'synthetic-updater.service', apply=True,
                    control=self._file_control, probe=self.probe)
            os._exit(1)
        self.assertEqual(os.waitpid(pid, 0)[1], 93 << 8)
        self.assertFalse(json.loads((self.root / 'synthetic-service.json').read_text())['active'])
        identifier = next((self.root / 'updater-upgrades').iterdir()).name
        with self.assertRaisesRegex(ValueError, '--recover.*' + identifier):
            self.apply()
        return identifier

    def _recover(self, identifier: str, enabled=True) -> dict:
        return recover_upgrade(self.root / 'policy.json', 'synthetic-updater.service', identifier,
            apply=enabled, control=self._file_control,
            probe=lambda root: {**self.probe(root), 'migration_capability': False})

    def _assert_original(self) -> None:
        self.assertEqual(json.loads((self.root / 'policy.json').read_text()), self.policy)
        self.assertEqual(json.loads((self.root / 'state.json').read_text()), self.state)
        for name, raw in self.before.items():
            self.assertEqual((self.root / 'source' / name).read_bytes(), raw)
        self.assertTrue(json.loads((self.root / 'synthetic-service.json').read_text())['active'])

    def test_source_kill_recovery_preview_and_repeat(self) -> None:
        """真实进程终止后停机预览、按原 UUID 恢复及重复恢复。@return None。"""
        identifier = self._interrupt_upgrade('source')
        self.calls.clear()
        value = self._recover(identifier, False)
        self.assertEqual(value['status'], 'recovery-planned')
        self.assertFalse(any(args[0] in ('stop', 'start') for args in self.calls))
        self.assertEqual(self._recover(identifier)['status'], 'recovered')
        self._assert_original()
        self.assertEqual(self._recover(identifier)['status'], 'recovered')
        self._assert_original()

    def test_policy_kill_recovery(self) -> None:
        """策略升级已落盘而状态尚为原值时恢复同一操作。@return None。"""
        identifier = self._interrupt_upgrade('policy')
        self.assertEqual(self._recover(identifier)['status'], 'recovered')
        self._assert_original()

    def test_state_kill_recovery(self) -> None:
        """源码、策略及状态均已替换而服务停机时恢复。@return None。"""
        identifier = self._interrupt_upgrade('state')
        self.assertEqual(self._recover(identifier)['status'], 'recovered')
        self._assert_original()

    def test_recovery_process_kill_resumes_original_uuid(self) -> None:
        """恢复自身在文件替换后终止仍沿原 UUID 完成。@return None。"""
        identifier = self._interrupt_upgrade('state')
        pid = os.fork()
        if pid == 0:
            def write_text(path, value, *args, **kwargs):
                atomic_text(path, value, *args, **kwargs)
                if path == self.root / 'source/deploy/v3/system_updater.py':
                    os._exit(94)
            with patch.object(upgrade_module, 'atomic_text', write_text):
                self._recover(identifier)
            os._exit(1)
        self.assertEqual(os.waitpid(pid, 0)[1], 94 << 8)
        self.assertEqual(json.loads((self.root / 'updater-upgrades' / identifier / 'upgrade.json').read_text())['state'], 'recovering')
        self.assertEqual(self._recover(identifier)['status'], 'recovered')
        self._assert_original()

    def test_recovery_preserves_later_state_and_foreign_source(self) -> None:
        """后来操作、维护门禁与外来源码变化均保留现场。@return None。"""
        identifier = self._interrupt_upgrade('source')
        original = (self.root / 'state.json').read_text()
        atomic_json(self.root / 'state.json', {**self.state, 'revision': 'later-revision'})
        with self.assertRaisesRegex(ValueError, '后来操作'):
            self._recover(identifier)
        self.assertEqual(json.loads((self.root / 'state.json').read_text())['revision'], 'later-revision')
        atomic_text(self.root / 'state.json', original)
        gate = self.root / 'gate/admission.json'
        value = json.loads(gate.read_text())
        atomic_json(gate, {**value, 'phase': 'draining', 'operation_id': identifier})
        with self.assertRaises(ValueError):
            self._recover(identifier)
        atomic_json(gate, value)
        target = self.root / 'source/deploy/v3/system_updater.py'
        atomic_text(target, '# 外来源码修改\n')
        with self.assertRaisesRegex(ValueError, '外来源码'):
            self._recover(identifier)
        self.assertEqual(target.read_text(), '# 外来源码修改\n')

    def test_recovery_rejects_tampered_backup_and_future_upgrade(self) -> None:
        """恢复副本摘要与后续接入记录保护原操作边界。@return None。"""
        identifier = self._interrupt_upgrade('source')
        backup = self.root / 'updater-upgrades' / identifier / 'before-policy.json'
        original = backup.read_text()
        atomic_text(backup, original + ' ')
        with self.assertRaisesRegex(ValueError, '副本摘要'):
            self._recover(identifier)
        atomic_text(backup, original)
        self._recover(identifier)
        self.apply()
        with self.assertRaisesRegex(ValueError, '后续接入'):
            self._recover(identifier)


if __name__ == '__main__':
    unittest.main()
