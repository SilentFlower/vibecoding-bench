"""实际 SQLite 元数据与软件字段恢复的边界验证。"""
import copy
import json
import sqlite3
import tempfile
import unittest
import uuid
import gc
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock

from system_update_host import HostDeployment
from runtime_files import atomic_json
from system_update_gate import read_gate
from system_update_database import assert_quiescent, create_snapshot, restore_snapshot


class HostMetadataTests(unittest.TestCase):
    """核对软件字段、账号身份及结构证据的真实持久效果。"""

    def setUp(self) -> None:
        """建立独立双库和合成画像。@return None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name in ('bench', 'gateway'):
            (self.root / name).mkdir()
        with sqlite3.connect(self.root / 'bench/db.sqlite') as database:
            database.execute('CREATE TABLE account_environments(environment_id TEXT,name TEXT,account_id INTEGER,fingerprint_json TEXT)')
            database.execute('INSERT INTO account_environments VALUES(?,?,?,?)', ('synthetic', 'synthetic', 1, '{"memory":"1536m","device":"synthetic"}'))
            database.execute('CREATE TABLE accounts(id INTEGER,name TEXT,profile_path TEXT,cc2api_account_id INTEGER)')
            database.execute('INSERT INTO accounts VALUES(1,"synthetic","profiles/synthetic",1)')
            for name in ('account_credential_ownerships', 'local_credential_authorizations'):
                database.execute('CREATE TABLE ' + name + '(account_id INTEGER,record_json TEXT)')
        self.environment = {'version': 'old', 'node_version': 'old-node', 'device_id': 'synthetic-private-device',
            'unknown': {'keep': True}, 'timezone': 'Asia/Tokyo'}
        with sqlite3.connect(self.root / 'gateway/gateway.sqlite') as database:
            database.execute('CREATE TABLE accounts(id INTEGER PRIMARY KEY,canonical_env TEXT,email TEXT,device_id TEXT,account_uuid TEXT,organization_uuid TEXT)')
            database.execute('CREATE TABLE oauth_account_ownerships(account_id INTEGER,record_json TEXT)')
            database.execute('INSERT INTO accounts(id,canonical_env) VALUES(?,?)', (1, json.dumps(self.environment)))
        self.host = HostDeployment({'state_root': str(self.root / 'updates'), 'data_root': str(self.root),
            'env_file': str(self.root / 'v3.env')})

    def change(self, value: dict) -> None:
        """更新合成画像。:param value: 新值。@return None。"""
        with sqlite3.connect(self.root / 'gateway/gateway.sqlite') as database:
            database.execute('UPDATE accounts SET canonical_env=? WHERE id=1', (json.dumps(value),))

    def test_software_compensation_preserves_identity_unknown_and_absent_fields(self) -> None:
        """仅补偿声明的四个字段，缺失和存在 null 保持区别。@return None。"""
        before = self.host.metadata()
        value = {**self.environment, 'version': 'new', 'version_base': None, 'build_time': 'new-time'}
        self.change(value)
        after = self.host.metadata()
        self.assertEqual(before['identity_sha256'], after['identity_sha256'])
        self.host.restore_software(before['software'], after['software'])
        with sqlite3.connect(self.root / 'gateway/gateway.sqlite') as database:
            restored = json.loads(database.execute('SELECT canonical_env FROM accounts').fetchone()[0])
        self.assertEqual(restored, self.environment)
        self.assertEqual(self.host.metadata(), before)

    def test_software_conflict_rolls_back_transaction(self) -> None:
        """迟到的软件恢复遇到并发变化时事务保持原数据。@return None。"""
        before = self.host.metadata()
        self.change({**self.environment, 'version': 'observed'})
        observed = self.host.metadata()
        self.change({**self.environment, 'version': 'concurrent'})
        with self.assertRaisesRegex(ValueError, '并发变化'):
            self.host.restore_software(before['software'], observed['software'])
        with sqlite3.connect(self.root / 'gateway/gateway.sqlite') as database:
            self.assertEqual(json.loads(database.execute('SELECT canonical_env FROM accounts').fetchone()[0])['version'], 'concurrent')

    def test_identity_and_schema_changes_are_visible(self) -> None:
        """设备、资源和数据库结构变化均能被独立证据识别。@return None。"""
        before = self.host.metadata()
        changed = copy.deepcopy(self.environment)
        changed['device_id'] = 'different'
        self.change(changed)
        self.assertNotEqual(self.host.metadata()['identity_sha256'], before['identity_sha256'])
        self.change(self.environment)
        with sqlite3.connect(self.root / 'bench/db.sqlite') as database:
            database.execute('ALTER TABLE account_environments ADD COLUMN changed TEXT')
        after = self.host.metadata()
        self.assertEqual(after['identity_sha256'], before['identity_sha256'])
        self.assertNotEqual(after['database_schema']['bench'], before['database_schema']['bench'])

    def test_metadata_closes_database_descriptors_before_snapshot(self) -> None:
        """元数据读取结束后释放持库句柄，明确识别仍在运行的读取者。@return None。"""
        gc.collect()
        self.host.metadata()
        assert_quiescent(self.root)
        with closing(sqlite3.connect(self.root / 'bench/db.sqlite')) as database:
            database.execute('SELECT * FROM accounts').fetchall()
            with self.assertRaisesRegex(ValueError, '仍有本机进程'):
                assert_quiescent(self.root)
        assert_quiescent(self.root)

    def test_snapshot_restore_retains_registered_role_recovery_and_generation(self) -> None:
        """双库恢复后保留候选角色收口登记，事务回执中断可幂等续接。@return None。"""
        gc.collect()
        with closing(sqlite3.connect(self.root / 'bench/db.sqlite')) as database, database:
            for name, kind in [('generation', 'INTEGER DEFAULT 4'), ('container_id', 'TEXT'),
                    ('network_container_id', 'TEXT'), ('sender_container_id', 'TEXT'),
                    ('state', "TEXT DEFAULT 'ready'"), ('isolation_version', 'INTEGER DEFAULT 2')]:
                database.execute('ALTER TABLE account_environments ADD COLUMN ' + name + ' ' + kind)
        operation = {'operation_id': str(uuid.uuid4()), 'epoch': str(uuid.uuid4()),
            'original': {'release': {'release': 'system-ci-1-1'}}, 'environment_intents': {'synthetic': {'generation': 4}}}
        folder = self.root / 'snapshot'
        create_snapshot(self.root, folder, 'test', operation)
        with closing(sqlite3.connect(self.root / 'bench/db.sqlite')) as database, database:
            database.execute("UPDATE account_environments SET generation=5,container_id='candidate-cli',network_container_id='candidate-network',sender_container_id='candidate-sender'")
        self.host.capture_restore_bindings(operation, folder, lambda: None)
        restore_snapshot(self.root, folder, 'test', operation, lambda: None)
        before_receipt = copy.deepcopy(operation)
        with self.assertRaisesRegex(RuntimeError, '合成回执中断'):
            self.host.restore_environment_bindings(operation, Mock(side_effect=RuntimeError('合成回执中断')))
        operation = before_receipt
        self.host.restore_environment_bindings(operation, lambda: None)
        with closing(sqlite3.connect(self.root / 'bench/db.sqlite')) as database:
            self.assertEqual(database.execute('SELECT generation,container_id FROM account_environments').fetchone(), (5, 'candidate-cli'))
        operation['environment_restore_bindings_applied'] = False
        with closing(sqlite3.connect(self.root / 'bench/db.sqlite')) as database, database:
            database.execute('UPDATE account_environments SET generation=6')
        with self.assertRaisesRegex(ValueError, '后来或外来'):
            self.host.restore_environment_bindings(operation, lambda: None)

    def test_binding_and_credential_ownership_changes_are_visible(self) -> None:
        """账号绑定和单一凭据所有权属于受保护身份。@return None。"""
        before = self.host.metadata()
        with sqlite3.connect(self.root / 'bench/db.sqlite') as database:
            database.execute('UPDATE accounts SET cc2api_account_id=2 WHERE id=1')
        self.assertNotEqual(self.host.metadata()['identity_sha256'], before['identity_sha256'])
        with sqlite3.connect(self.root / 'bench/db.sqlite') as database:
            database.execute('UPDATE accounts SET cc2api_account_id=1 WHERE id=1')
        self.assertEqual(self.host.metadata()['identity_sha256'], before['identity_sha256'])
        with sqlite3.connect(self.root / 'gateway/gateway.sqlite') as database:
            database.execute('INSERT INTO oauth_account_ownerships VALUES(1,?)', ('{"owner":"changed"}',))
        self.assertNotEqual(self.host.metadata()['identity_sha256'], before['identity_sha256'])

    def test_restore_reacquires_released_gate_before_observing_new_work(self) -> None:
        """提交后恢复先重新关门，后来活动保持且切换尚未开始。@return None。"""
        operation = self.prepare_restore_gate('idle')
        self.host.request = Mock(side_effect=[{'active': 0, 'environments': []}, {'active': 1}])
        self.host.verify_images = Mock()
        with self.assertRaisesRegex(ValueError, '恢复前仍有在途'):
            self.host.restore(operation, lambda: None)
        self.assertEqual(read_gate(self.host.gate, 'test')['phase'], 'blocked')
        self.host.verify_images.assert_not_called()

    def test_fenced_restore_can_reach_images_when_candidate_api_is_down(self) -> None:
        """原门禁持续关闭时，可恢复尚未启动的候选控制服务。@return None。"""
        operation = self.prepare_restore_gate('blocked')
        self.host.request = Mock(side_effect=RuntimeError('候选 API 尚未启动'))
        self.host.verify_images = Mock(side_effect=ValueError('到达原版镜像核验'))
        with self.assertRaisesRegex(ValueError, '到达原版镜像核验'):
            self.host.restore(operation, lambda: None)
        self.host.request.assert_not_called()

    def prepare_restore_gate(self, phase: str) -> dict:
        """建立同操作的实际持久门禁。:param phase: 原阶段。@return 恢复输入。"""
        self.host.policy['deployment'] = 'test'
        self.host.gate.mkdir(parents=True)
        operation = {'operation_id': str(uuid.uuid4()), 'epoch': str(uuid.uuid4()), 'revision': str(uuid.uuid4()),
            'target': {'release': 'system-ci-1-1'}, 'created_at': '2026-11-11T00:00:00Z', 'original': {'selection': {}}}
        atomic_json(self.host.gate / 'admission.json', {'schema_version': 1, 'deployment': 'test',
            'operation_id': operation['operation_id'] if phase == 'blocked' else None, 'epoch': operation['epoch'],
            'revision': operation['revision'], 'phase': phase, 'target_release': 'system-ci-1-1' if phase == 'blocked' else None,
            'created_at': operation['created_at']})
        return operation


if __name__ == '__main__':
    unittest.main()
