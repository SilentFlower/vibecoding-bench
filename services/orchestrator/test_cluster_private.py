"""使用真实文件权限核对SSH安装门禁接管及维护状态保留。"""
from __future__ import annotations

import os
import json
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path

from cluster_private import initialize_node_private
from cluster_ssh import _BOOTSTRAP_SCRIPT
from runtime_files import atomic_json
from system_update_gate import read_gate


@unittest.skipUnless(os.geteuid() == 0, '节点容器门禁接管验证需要隔离开发环境的root')
class NodePrivateTests(unittest.TestCase):
    """真实UID与无链接读取覆盖安装用户交接。"""

    def setUp(self) -> None:
        """建立含blocked记录的临时节点根。:return: None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.data, self.key = Path(temporary.name), 'a' * 32
        self.marker = self.data / 'cluster-node.json'
        self.gate = self.data / 'system-update-gate'
        self.gate.mkdir(mode=0o700)
        atomic_json(self.marker, {'protocol': 1, 'node_key': self.key, 'deployment_id': 'synthetic'})
        self.record = self.gate / 'admission.json'
        self.value = {'schema_version': 1, 'deployment': 'synthetic', 'phase': 'blocked',
            'operation_id': str(uuid.uuid4()), 'epoch': str(uuid.uuid4()), 'revision': str(uuid.uuid4()),
            'target_release': 'synthetic-release', 'created_at': '2026-11-17T00:00:00Z'}
        atomic_json(self.record, self.value)

    def test_nonroot_installation_handoff_preserves_blocked_bytes(self) -> None:
        """原安装用户保留数据根，容器root接管门禁且重复接管幂等。:return: None。"""
        before = self.record.read_bytes()
        for path in (self.data, self.marker, self.gate, self.record):
            os.chown(path, 65534, 65534)
        for _ in range(2):
            initialize_node_private(self.data, self.key, 'synthetic')
            self.assertEqual(before, self.record.read_bytes())
            self.assertEqual(self.value, read_gate(self.gate, 'synthetic'))
            self.assertEqual([0, 0], [path.stat().st_uid for path in (self.gate, self.record)])
            self.assertEqual([65534, 65534], [path.stat().st_uid for path in (self.data, self.marker)])

    def test_invalid_record_is_rejected_before_changing_ownership(self) -> None:
        """错部署或坏阶段保持原UID与字节供恢复。:return: None。"""
        for change in ({'phase': 'unknown'}, {'deployment': 'other'}):
            with self.subTest(change=change):
                atomic_json(self.record, {**self.value, **change})
                os.chown(self.gate, 65534, 65534)
                os.chown(self.record, 65534, 65534)
                os.chown(self.marker, 65534, 65534)
                before = self.record.read_bytes()
                with self.assertRaises(ValueError):
                    initialize_node_private(self.data, self.key, 'synthetic')
                self.assertEqual(before, self.record.read_bytes())
                self.assertEqual(65534, self.record.stat().st_uid)
                self.assertEqual(65534, self.gate.stat().st_uid)

    def test_foreign_owner_public_mode_and_symlink_are_rejected(self) -> None:
        """未知UID、公开权限或链接记录均阻止服务就绪。:return: None。"""
        os.chown(self.record, 65533, 65533)
        with self.assertRaises(ValueError):
            initialize_node_private(self.data, self.key, 'synthetic')
        os.chown(self.record, 0, 0)
        self.record.chmod(0o644)
        with self.assertRaises(ValueError):
            initialize_node_private(self.data, self.key, 'synthetic')
        self.record.chmod(0o600)
        target = self.gate / 'original.json'
        self.record.rename(target)
        self.record.symlink_to(target)
        with self.assertRaises(OSError):
            initialize_node_private(self.data, self.key, 'synthetic')

    def test_actual_nonroot_bootstrap_can_recheck_root_owned_gate(self) -> None:
        """真实非root进程二次纳管保留root门禁，缺失门禁要求恢复。:return: None。"""
        self.data.chmod(0o755)
        data = self.data / 'nonroot-node'
        data.mkdir(mode=0o700)
        os.chown(data, 65534, 65534)
        payload = json.dumps({'data_root': str(data), 'node_key': self.key, 'deployment_id': 'synthetic'}).encode()

        def bootstrap():
            return subprocess.run(['/usr/bin/python3', '-c', _BOOTSTRAP_SCRIPT], input=payload,
                capture_output=True, user=65534, group=65534, extra_groups=(), timeout=5, check=False)

        self.assertEqual(0, bootstrap().returncode)
        initialize_node_private(data, self.key, 'synthetic')
        before = (data / 'system-update-gate/admission.json').read_bytes()
        self.assertEqual(0, bootstrap().returncode)
        self.assertEqual(before, (data / 'system-update-gate/admission.json').read_bytes())
        (data / 'system-update-gate').rename(data / 'original-gate')
        self.assertNotEqual(0, bootstrap().returncode)
        self.assertFalse((data / 'system-update-gate').exists())


if __name__ == '__main__':
    unittest.main()
