"""节点许可在慢准备及终端缓冲投递边界的定向验证。"""
from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pi_terminal import PiTerminal
import test_cluster_lease_mirror as mirror_fixture


class NodeInputAdmissionTests(unittest.TestCase):
    """使用原运行时、原Pi输入和真实私有证明，Docker仅作离线替身。"""

    def setUp(self) -> None:
        """建立持有中央原证明的节点运行时。:return: None。"""
        fixture = mirror_fixture.NodeLeaseMirrorTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture, self.runtime = fixture, fixture.runtime

    def test_expiry_during_version_install_rejects_before_cli_setup_yields(self) -> None:
        """安装耗时跨过截止时，实际CLI启动继续保持关闭。:return: None。"""
        fixture = self.fixture

        def slow_version(*args):
            fixture.fixture.now = 1021

        with patch.object(self.runtime, 'ensure', return_value=(fixture.row, Mock())), \
                patch.object(self.runtime, 'check_system_profile'), \
                patch.object(self.runtime, '_ensure_version', side_effect=slow_version), \
                patch.object(self.runtime, 'cleanup') as cleanup, fixture.mirror.preparing(fixture.scope):
            with self.assertRaisesRegex(ValueError, '过期'):
                with self.runtime._cli_setup(fixture.account, fixture.scope.source, '2.1.303',
                        idle_only=True, shared_cli=True):
                    self.fail('超期准备不能返回启动权限')
            cleanup.assert_called_once()
        self.runtime.client.api.exec_start.assert_not_called()

    def test_expiry_during_terminal_buffer_upload_blocks_paste_and_enter(self) -> None:
        """文本只装入临时buffer后超期，paste及Enter前再次核对原证明。:return: None。"""
        fixture = self.fixture
        job = fixture.claim()
        job.update(tmux_socket='/run/v3/jobs/synthetic/tmux.sock', tmux='projects-synthetic')
        terminal = PiTerminal(self.runtime, Mock(), Mock(), namespace='projects')
        raw, stream = Mock(), Mock()
        stream._sock = raw

        def after_upload(*args):
            fixture.fixture.now = 1021
            return b''

        raw.recv.side_effect = after_upload
        self.runtime.client.api.exec_create.return_value = {'Id': 'synthetic-buffer'}
        self.runtime.client.api.exec_start.return_value = stream
        self.runtime.client.api.exec_inspect.return_value = {'ExitCode': 0}
        container = SimpleNamespace(id='synthetic-cli', exec_run=Mock())
        with patch.object(self.runtime, '_container', return_value=container):
            with self.assertRaisesRegex(RuntimeError, '输入结果未知'):
                terminal.send({'runtime_json': json.dumps({'token': job['token']})}, 'synthetic-input', '合成输入', [], True)
        self.assertEqual(1, container.exec_run.call_count)
        self.assertEqual('delete-buffer', container.exec_run.call_args.args[0][3])
        stream.close.assert_called_once()
        self.assertTrue(self.runtime._owns_job(job))
        self.assertEqual('active', fixture.store.get(fixture.scope)['phase'])


if __name__ == '__main__':
    unittest.main()
