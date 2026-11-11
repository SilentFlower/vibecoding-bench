"""首次接入默认预览、固定来源复制及部署配置 CAS 的离线验证。"""
import hashlib
import fcntl
import json
import os
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import test_system_release as release_tests
from install_system_updater import finalize_installation, prepare_installation
from runtime_files import atomic_json, atomic_text
from system_update_contract import strict_json, safe_read
from system_update_gate import read_gate


class BootstrapHost:
    """合成宿主边界，真实执行文件安装、签名及最终提交逻辑。"""

    def __init__(self, policy: dict) -> None:
        """绑定临时策略。:param policy: 合成部署。@return None。"""
        self.policy = policy

    def values(self) -> dict:
        """提供已核对的合成环境。@return 环境值。"""
        return {}

    def verify_images(self, *args) -> dict:
        """模拟精确镜像核验。:param args: 来源。@return 镜像状态。"""
        return {'control': {'Id': 'sha256:' + 'a' * 64}}

    def metadata(self) -> dict:
        """提供固定身份摘要。@return 无凭据元数据。"""
        return {'identity_sha256': 'b' * 64, 'software': {}}

    def controls(self) -> dict:
        """提供实际控制服务结构。@return 两个控制服务。"""
        return {role: {'Id': role, 'Image': 'sha256:' + 'a' * 64, 'State': {'Status': 'running'}} for role in ('gateway', 'orchestrator')}

    def drained(self, *args) -> dict:
        """模拟完整排空。:param args: 原接入。@return 就绪。"""
        return {'ready': True}

    def release(self, operation: dict) -> None:
        """实际按原身份释放临时门禁。:param operation: 原接入。@return None。"""
        root = Path(self.policy['state_root'])
        gate = read_gate(root / 'gate', self.policy['deployment'])
        if gate['operation_id'] != operation['operation_id'] or gate['epoch'] != operation['epoch']:
            raise ValueError('合成接入身份变化')
        atomic_json(root / 'gate/admission.json', {**gate, 'phase': 'idle', 'operation_id': None, 'target_release': None})


class SystemInstallTests(unittest.TestCase):
    """首次接入和最终配置提交的实际文件测试。"""

    def setUp(self) -> None:
        """生成合成签名、私有配置及独立目录。@return None。"""
        fixture = release_tests.SystemReleaseTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.env = fixture.root / 'v3.env'
        self.data = fixture.root / 'business'
        self.data.mkdir()
        self.root = fixture.root / 'updates'
        atomic_text(self.env, f'V3_DEPLOYMENT_ID=test\nV3_DATA_ROOT={self.data}\nV3_ADMIN_PASSWORD=synthetic-private\nV3_ACCOUNT_MEMORY=1536m\n')

    def prepare(self, apply=False) -> dict:
        """执行同一接入计划。:param apply: 是否显式写入。@return 计划。"""
        return prepare_installation(self.env, self.fixture.output, self.root, self.fixture.public, apply=apply, backend_type=BootstrapHost)

    def test_dry_run_and_independent_installed_sources(self) -> None:
        """默认预览保持配置；显式接入复制固定依赖并保留私有权限。@return None。"""
        before = self.env.read_bytes()
        self.assertEqual(self.prepare()['status'], 'planned')
        self.assertFalse(self.root.exists())
        self.assertEqual(self.prepare(True)['status'], 'prepared')
        self.assertEqual(self.env.read_bytes(), before)
        self.assertEqual((self.root / 'socket/token').stat().st_mode & 0o777, 0o600)
        self.assertTrue((self.root / 'source/deploy/v3/system_updater.py').is_file())
        self.assertTrue((self.root / 'source/orchestrator/system_update_gate.py').is_file())
        self.assertEqual(read_gate(self.root / 'gate', 'test')['phase'], 'blocked')
        preview = finalize_installation(self.root / 'policy.json', backend_type=BootstrapHost)
        self.assertEqual(preview['status'], 'verified')
        self.assertEqual(self.env.read_bytes(), before)
        final = finalize_installation(self.root / 'policy.json', apply=True, backend_type=BootstrapHost)
        self.assertEqual(final['status'], 'installed')
        self.assertIn(b'V3_ACCOUNT_MEMORY=1536m', self.env.read_bytes())
        self.assertIn(b'V3_ADMIN_PASSWORD=synthetic-private', self.env.read_bytes())
        self.assertIn(b'V3_ACCOUNT_RELEASE=ci-123-1', self.env.read_bytes())
        self.assertFalse(strict_json(safe_read(self.root / 'state.json'))['bootstrap_pending'])
        self.assertEqual(read_gate(self.root / 'gate', 'test')['phase'], 'idle')

    def test_changed_deployment_configuration_blocks_final_commit(self) -> None:
        """外部配置变化阻断最终覆盖，原门禁保持。@return None。"""
        self.prepare(True)
        atomic_text(self.env, self.env.read_text() + 'V3_HOST_PORT=18081\n')
        with self.assertRaisesRegex(ValueError, '配置已经变化'):
            finalize_installation(self.root / 'policy.json', apply=True, backend_type=BootstrapHost)
        self.assertIn(b'18081', self.env.read_bytes())
        self.assertEqual(read_gate(self.root / 'gate', 'test')['phase'], 'blocked')

    def test_restart_between_state_commit_and_gate_release_finishes_original(self) -> None:
        """状态提交后的中断可重试原接入，安装时间和门禁代次保持。@return None。"""
        self.prepare(True)
        with patch.object(BootstrapHost, 'release', side_effect=OSError('合成释放中断')):
            with self.assertRaises(OSError):
                finalize_installation(self.root / 'policy.json', apply=True, backend_type=BootstrapHost)
        state = strict_json(safe_read(self.root / 'state.json'))
        gate = read_gate(self.root / 'gate', 'test')
        self.assertFalse(state['bootstrap_pending'])
        self.assertEqual(gate['phase'], 'blocked')
        self.assertEqual(finalize_installation(self.root / 'policy.json', backend_type=BootstrapHost)['status'], 'verified')
        self.assertEqual(read_gate(self.root / 'gate', 'test'), gate)
        self.assertEqual(finalize_installation(self.root / 'policy.json', apply=True, backend_type=BootstrapHost)['status'], 'installed')
        self.assertEqual(read_gate(self.root / 'gate', 'test')['phase'], 'idle')
        self.assertEqual(strict_json(safe_read(self.root / 'state.json'))['current']['installed_at'], state['current']['installed_at'])
        self.assertEqual(finalize_installation(self.root / 'policy.json', apply=True, backend_type=BootstrapHost)['status'], 'installed')

    def test_restart_after_gate_release_is_an_idempotent_completion(self) -> None:
        """释放已经落盘后的回包中断可按同一完成记录重试。@return None。"""
        self.prepare(True)
        release = BootstrapHost.release
        def interrupt(backend, operation):
            release(backend, operation)
            raise OSError('合成完成回包中断')
        with patch.object(BootstrapHost, 'release', interrupt), self.assertRaises(OSError):
            finalize_installation(self.root / 'policy.json', apply=True, backend_type=BootstrapHost)
        gate = read_gate(self.root / 'gate', 'test')
        self.assertEqual(gate['phase'], 'idle')
        self.assertEqual(finalize_installation(self.root / 'policy.json', apply=True, backend_type=BootstrapHost)['status'], 'installed')
        self.assertEqual(read_gate(self.root / 'gate', 'test'), gate)

    def test_foreign_gate_and_newer_installation_are_never_overwritten(self) -> None:
        """首次接入重试只承接原归属，后来操作保持。@return None。"""
        self.prepare(True)
        gate = read_gate(self.root / 'gate', 'test')
        atomic_json(self.root / 'gate/admission.json', {**gate, 'operation_id': str(uuid.uuid4())})
        with self.assertRaisesRegex(ValueError, '门禁归属'):
            finalize_installation(self.root / 'policy.json', apply=True, backend_type=BootstrapHost)
        atomic_json(self.root / 'gate/admission.json', gate)
        state = strict_json(safe_read(self.root / 'state.json'))
        atomic_json(self.root / 'state.json', {**state, 'revision': str(uuid.uuid4())})
        with self.assertRaisesRegex(ValueError, '已有其他操作'):
            finalize_installation(self.root / 'policy.json', apply=True, backend_type=BootstrapHost)
        self.assertEqual(read_gate(self.root / 'gate', 'test'), gate)

    def test_live_updater_lock_blocks_first_installation_commit(self) -> None:
        """复用执行器进程锁，防止并发写入安装记录。@return None。"""
        self.prepare(True)
        descriptor = os.open(self.root / 'service.lock', os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError, '先停止独立更新服务'):
                finalize_installation(self.root / 'policy.json', apply=True, backend_type=BootstrapHost)
            self.assertTrue(strict_json(safe_read(self.root / 'state.json'))['bootstrap_pending'])
        finally:
            os.close(descriptor)


if __name__ == '__main__':
    unittest.main()
