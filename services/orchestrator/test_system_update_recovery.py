"""部分账号角色恢复的归属、镜像及真实活动证明边界。"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from system_updates import _rollout_lease, partial_restore_ready


class PartialRecoveryTests(unittest.TestCase):
    """独立验证部分恢复的阻断条件，实际 Docker 场景由验收入口覆盖。"""

    def setUp(self) -> None:
        """建立合成角色与原操作镜像集合。@return None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.row = {'environment_id': 'synthetic', 'container_id': 'cli', 'sender_container_id': None,
            'network_container_id': None, 'generation': 2}
        self.image = 'sha256:' + 'a' * 64
        self.container = SimpleNamespace(id='cli', labels={'vibebench.role': 'account'}, attrs={'Image': self.image},
            status='running', reload=lambda: None, exec_run=Mock(return_value=SimpleNamespace(exit_code=0, output=b'{"orphans":[]}')))
        self.runtime = SimpleNamespace(deployment='test', _root=lambda row: self.root,
            environment_jobs=lambda eid: [], _execution_records=lambda row: [], _running_sender_active=lambda row: 0,
            client=SimpleNamespace(containers=SimpleNamespace(list=lambda **kwargs: [self.container])))
        gate = patch('system_updates.UPDATE_GATE', SimpleNamespace(state=lambda: {'active': 0}))
        roles = patch('system_updates.role_container', return_value=self.container)
        gate.start()
        roles.start()
        self.addCleanup(gate.stop)
        self.addCleanup(roles.stop)

    def test_known_partial_roles_can_restore_and_unknown_image_is_rejected(self) -> None:
        """受信部分角色可收口，其他镜像拒绝。@return None。"""
        partial_restore_ready(self.runtime, self.row, None, [self.image])
        with self.assertRaisesRegex(ValueError, '以外的镜像'):
            partial_restore_ready(self.runtime, self.row, None, ['sha256:' + 'b' * 64])

    def test_orphan_process_and_unregistered_container_block_restore(self) -> None:
        """未知进程与未登记实例均保留现场。@return None。"""
        self.container.exec_run.return_value.output = b'{"orphans":[123]}'
        with self.assertRaisesRegex(ValueError, 'CLI 活动'):
            partial_restore_ready(self.runtime, self.row, None, [self.image])
        self.container.exec_run.return_value.output = b'{"orphans":[]}'
        self.container.id = 'unregistered'
        with self.assertRaisesRegex(ValueError, '未登记角色'):
            partial_restore_ready(self.runtime, self.row, None, [self.image])

    def test_persistent_execution_and_sender_activity_block_restore(self) -> None:
        """磁盘执行意图和真实发送活动独立阻断。@return None。"""
        (self.root / 'runtime').mkdir()
        execution = self.root / 'runtime/execution.json'
        execution.write_text('{}')
        with self.assertRaisesRegex(ValueError, '持久执行'):
            partial_restore_ready(self.runtime, self.row, None, [self.image])
        execution.unlink()
        self.runtime._running_sender_active = lambda row: 1
        with self.assertRaisesRegex(ValueError, '发送器活动'):
            partial_restore_ready(self.runtime, self.row, None, [self.image])

    def test_rolling_lease_accepts_its_own_holder_and_rejects_foreign_activity(self) -> None:
        """租约快照同时在 lease 和 holders 投影排他租约。@return 无。"""
        own = {'owner': 'maintenance:system-update:synthetic', 'generation': 'original', 'exclusive': True}
        replacement = {**own, 'generation': 'renewed', 'phase': 'claimed'}
        original = {'lease': own, 'holders': [own]}
        current = {'lease': replacement, 'holders': [replacement]}
        self.runtime.gateway = Mock()
        self.runtime.gateway._request.side_effect = [original, {}, current, current, current, {}]
        with _rollout_lease(self.runtime, 7, own['owner']) as proof:
            partial_restore_ready(self.runtime, self.row, {'cc2api_account_id': 7},
                [self.image], lease_proof=proof, rolling=True)
        self.runtime.gateway._request.side_effect = None
        self.runtime.gateway._request.return_value = {**current, 'holders': [replacement, {**own, 'owner': 'other'}]}
        with self.assertRaisesRegex(ValueError, '账号租约'):
            partial_restore_ready(self.runtime, self.row, {'cc2api_account_id': 7},
                [self.image], lease_proof=proof, rolling=True)


if __name__ == '__main__':
    unittest.main()
