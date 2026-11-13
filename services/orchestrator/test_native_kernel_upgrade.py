"""固定版本签名、账号门禁和异常恢复的离线回归。"""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import native_kernel_upgrade as upgrade


class FixtureRuntime:
    """模拟现有网关门禁与容器查询接口，使用真实持久目录。"""

    def __init__(self, root):
        self.data = root
        self.gateway = self
        self.lock = threading.RLock()
        self.config = {'binding': {'account_id': 7, 'environment_id': 'a' * 32, 'generation': 3},
                       'native': {'binary_path':'/usr/local/bin/ccrb-runtime'}}
        self.lease = None
        self.active = 0
        self.rejected = False
        self.events = []

    def _root(self, row):
        return self.data / row['environment_id']

    def _sender_config(self, row):
        return self._root(row) / 'runtime/sender.json'

    def environment_lock(self, environment_id):
        return self.lock

    def _write_sender_config(self, row, config):
        self.events.append(('config', config['native'].get('release')))
        self.config = json.loads(json.dumps(config))
        upgrade.atomic_json(self._sender_config(row), self.config)

    def _sender_active(self, row):
        return self.active

    def _request(self, method, path, body=None, **kwargs):
        if method == 'GET':
            result = {'active': self.active, 'lease': self.lease}
            if self.active:
                self.active -= 1
            return result
        if path.endswith('probe'):
            assert self.lease and self.lease['phase'] == 'claimed'
            target = body['target']
            self.events.append(('probe', target['release']))
            if self.rejected and target['release']:
                raise ConnectionError('候选不就绪')
            return {**body['binding'], **target, 'state': 'ready', 'pid': 210 + len(self.events), 'image_sha256': 'a' * 64}
        action = body['operation']
        self.events.append((action, self.active))
        if action == 'prepare':
            self.lease = {'owner': body['owner'], 'generation': str(uuid.uuid4()),
                          'phase': 'draining', 'expires_at': 10**12}
        else:
            assert self.lease and self.lease['generation'] == body['generation']
            if action == 'claim':
                assert self.active == 0
                self.lease['phase'] = 'claimed'
            elif action == 'release':
                self.lease = None
        return {'active': self.active, 'lease': self.lease}


class NativeKernelAvailabilityTest(unittest.TestCase):
    """验证发行信任根覆盖各原生环境，并保留缺失配置的拒绝行为。"""

    def test_all_native_environments_share_deployment_key(self):
        """旧试点配置保留时，两个环境仍分别提供管理状态。@return None。"""
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                'V3_NATIVE_RELEASE_PUBLIC_KEY': 'b' * 64,
                'V3_NATIVE_RELEASE_PILOT_ENVIRONMENT': 'a' * 32}):
            runtime = FixtureRuntime(Path(directory))
            for identity in ('a' * 32, 'c' * 32):
                row = {'environment_id': identity, 'generation': 1, 'sender_container_id': 'synthetic'}
                runtime._write_sender_config(row, {'binding': {'account_id': 7}, 'native': {'memory_mib': 0}})
                self.assertEqual(upgrade.release_key(), 'b' * 64)
                self.assertEqual(upgrade.status(runtime, row)['current']['release'], upgrade.VERSION)
                self.assertEqual(upgrade.status(runtime, row)['revision'], '1:initial')
            row = {'environment_id': 'c' * 32, 'generation': 1, 'sender_container_id': 'synthetic'}
            upgrade.atomic_json(runtime._sender_config(row), {'binding': {'account_id': 7}, 'native': None})
            self.assertIsNone(upgrade.status(runtime, row))

    def test_missing_or_invalid_public_key_keeps_management_disabled(self):
        """缺失、截短或非法公钥保持关闭状态。@return None。"""
        with tempfile.TemporaryDirectory() as directory:
            runtime = FixtureRuntime(Path(directory))
            row = {'environment_id': 'a' * 32, 'generation': 1, 'sender_container_id': 'synthetic'}
            runtime._write_sender_config(row, {'binding': {'account_id': 7}, 'native': {'memory_mib': 0}})
            for key in ('', 'b' * 63, 'z' * 64):
                with self.subTest(key=key), patch.dict(os.environ, {'V3_NATIVE_RELEASE_PUBLIC_KEY': key}):
                    self.assertEqual(upgrade.release_key(), '')
                    self.assertIsNone(upgrade.status(runtime, row))


class NativeKernelUpgradeTest(unittest.TestCase):
    """覆盖制品准入和受控切换的可观察合同。"""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'attachments'
        self.source.mkdir()
        self.release = 'v0.1.0-beta.4'
        self.binary = b'fixture distinct launcher'
        digest = hashlib.sha256(self.binary).hexdigest()
        self.reference = {'release': self.release, 'launcher_sha256': digest}
        manifest = {'schema_version': 1, **self.reference, 'platform': 'linux-x64',
            'asset': upgrade.ASSET, 'source_version': '2.1.293', 'source_sha256': upgrade.SOURCE,
            'launcher_bytes': len(self.binary), 'image_sha256': 'a' * 64, 'image_bytes': 4096,
            'worker_schema': 2, 'raw_input_protocol': 1, 'resource_contract': 1}
        (self.source / upgrade.ASSET).write_bytes(self.binary)
        metadata = self.source / 'runtime-release.json'
        metadata.write_text(json.dumps(manifest))
        key = self.root / 'private.pem'
        subprocess.run(['openssl', 'genpkey', '-algorithm', 'ed25519', '-out', key], check=True)
        public = subprocess.check_output(['openssl', 'pkey', '-in', key, '-pubout', '-outform', 'DER'])
        self.key = public[-32:].hex()
        subprocess.run(['openssl', 'pkeyutl', '-sign', '-rawin', '-inkey', key,
            '-in', metadata, '-out', self.source / 'runtime-release.sig'], check=True)
        self.runtime = FixtureRuntime(self.root)
        self.row = {'environment_id': 'a' * 32, 'generation': 3, 'sender_container_id': 'synthetic'}
        self.runtime._write_sender_config(self.row, self.runtime.config)
        self.runtime.events.clear()
        for mock in (
            patch.object(upgrade, 'release_key', return_value=self.key),
            patch.object(upgrade, '_context', side_effect=lambda rt, row, account: json.loads(json.dumps(rt.config))),
            patch.object(upgrade, '_download', side_effect=lambda url, path, limit: shutil.copyfile(self.source / path.name, path)),
            patch.object(upgrade.time, 'sleep'),
        ):
            mock.start()
            self.addCleanup(mock.stop)

    def operate(self, action, release=None, operation_id=None, revision=None):
        return upgrade.run_upgrade(self.runtime, self.row, 7, action,
            operation_id or str(uuid.uuid4()), release,
            self.reference['launcher_sha256'] if action == 'activate' else upgrade.SHA256 if action == 'rollback' else None,
            revision or upgrade.status(self.runtime, self.row)['revision'])

    def test_saved_release_remains_valid_when_becoming_builtin(self):
        """平台内置升级到持久选择时仍能重新验签缓存及读取状态。@return 无。"""
        with patch.object(upgrade, 'SHA256', self.reference['launcher_sha256']), patch.object(upgrade, 'VERSION', self.release):
            self.assertEqual(self.operate('prepare', self.release)['prepared'], self.reference)
            with patch.object(upgrade, '_download', side_effect=AssertionError('缓存应离线核验')):
                self.assertEqual(upgrade.stage_release(self.runtime.data / 'native-releases', self.release, self.key), self.reference)

    def test_签名或分发摘要错误保留运行版本(self):
        signature = self.source / 'runtime-release.sig'
        valid = signature.read_bytes()
        signature.write_bytes(bytes(64))
        with self.assertRaisesRegex(ValueError, '发布签名无效'):
            self.operate('prepare', self.release)
        signature.write_bytes(valid)
        (self.source / upgrade.ASSET).write_bytes(b'z' * len(self.binary))
        with self.assertRaisesRegex(ValueError, '分发文件摘要'):
            self.operate('prepare', self.release)
        self.assertEqual(self.runtime.events, [])
        self.assertIsNone(self.runtime.config['native'].get('release'))

    def test_准备独立于排空且回滚使用同一门禁(self):
        self.runtime.active = 2
        self.assertEqual(self.operate('prepare', self.release)['prepared'], self.reference)
        self.assertEqual(self.runtime.active, 2)
        self.assertEqual(self.runtime.events, [])
        operation = str(uuid.uuid4())
        revision = upgrade.status(self.runtime, self.row)['revision']
        result = self.operate('activate', self.release, operation, revision)
        self.assertEqual(result['current'], self.reference)
        self.assertEqual([event[0] for event in self.runtime.events],
                         ['prepare', 'claim', 'config', 'probe', 'release'])
        self.assertEqual(self.operate('activate', self.release, operation, revision), result)
        result = self.operate('rollback')
        self.assertEqual(result['current']['launcher_sha256'], upgrade.SHA256)
        self.assertEqual(result['previous'], self.reference)
        self.assertIsNone(self.runtime.lease)
        with self.assertRaisesRegex(ValueError, '操作状态已变化'):
            self.operate('activate', self.release, operation, revision)
        self.assertEqual(sum(event[0] == 'probe' for event in self.runtime.events), 2)
        self.assertEqual(upgrade.status(self.runtime, self.row)['current']['launcher_sha256'], upgrade.SHA256)

    def test_预热失败时原版经核验后再开放(self):
        self.operate('prepare', self.release)
        self.runtime.rejected = True
        result = self.operate('activate', self.release)
        self.assertEqual(result['state'], 'restored')
        self.assertEqual(self.runtime.events[-3:], [('config', None), ('probe', None), ('release', 0)])
        self.assertIsNone(result['previous'])
        self.assertIsNone(self.runtime.lease)

    def test_排空超时不写发送器配置(self):
        self.operate('prepare', self.release)
        self.runtime.active = 10
        with patch.object(upgrade.time, 'monotonic', side_effect=[0, 121]):
            result = self.operate('activate', self.release)
        self.assertEqual(result['state'], 'failed')
        self.assertNotIn('config', [event[0] for event in self.runtime.events])
        self.assertIsNone(self.runtime.lease)

    def test_中断对账保留门禁直到原版预热(self):
        self.operate('prepare', self.release)
        operation = str(uuid.uuid4())
        root = self.runtime._root(self.row)
        lease = self.runtime._request('POST', '/lease', {'operation': 'prepare', 'owner': 'kernel:' + operation})['lease']
        self.runtime._request('POST', '/lease', {'operation': 'claim', 'generation': lease['generation']})
        upgrade.atomic_json(root / 'runtime/native-kernel-upgrade.json', {
            'state': 'switching', 'operation_id': operation, 'account_id': 7, 'binding_generation': 3,
            'lease_generation': lease['generation'], 'target': self.reference, 'original': None,
        })
        self.assertTrue(upgrade.recover_interrupted(root))
        self.assertIsNotNone(self.runtime.lease)
        result = self.operate('recover')
        self.assertEqual(result['state'], 'restored')
        self.assertEqual(result['current']['launcher_sha256'], upgrade.SHA256)
        self.assertIsNone(self.runtime.lease)


    def test_排空中断释放已过期的原门禁(self):
        operation = str(uuid.uuid4())
        root = self.runtime._root(self.row)
        lease = self.runtime._request('POST', '/lease', {'operation': 'prepare', 'owner': 'kernel:' + operation})['lease']
        lease['expires_at'] = 0
        upgrade.atomic_json(root / 'runtime/native-kernel-upgrade.json', {
            'state': 'draining', 'operation_id': operation, 'account_id': 7, 'binding_generation': 3,
            'lease_generation': lease['generation'], 'target': self.reference, 'original': None,
        })
        self.assertTrue(upgrade.recover_interrupted(root))
        self.assertEqual(self.operate('recover')['state'], 'failed')
        self.assertIsNone(self.runtime.lease)
        self.assertNotIn('probe', [event[0] for event in self.runtime.events])

    def test_激活时摘要漂移不关闭入场(self):
        self.operate('prepare', self.release)
        with self.assertRaisesRegex(ValueError, '目标内核摘要已变化'):
            upgrade.run_upgrade(self.runtime, self.row, 7, 'activate', str(uuid.uuid4()), self.release, 'f' * 64, upgrade.status(self.runtime, self.row)['revision'])
        self.assertEqual(self.runtime.events, [])
