"""真实签名、双库快照与更新状态机的迁移集成回归。"""
import copy
import hashlib
import json
import sqlite3
import unittest
import uuid
from pathlib import Path

from system_release import create_index, create_release, sign_file, data_contracts, REPO
from runtime_files import atomic_json, atomic_text
from system_update_contract import validate_release
from system_update_database import create_snapshot, restore_snapshot, rotate_snapshots
from system_updater import SystemUpdater
import test_system_updater as updater_tests


def evidence_for(fixture, original: dict, raw: bytes) -> dict:
    """构造绑定真实临时签名来源的合成演练事实。

    :param fixture: 合成联合构建夹具。
    :param original: 已签名原版。
    :param raw: 原版签名材料的实际字节。
    :return: 仅供离线测试的证据。
    """
    return {'schema_version': 1, 'revision': fixture.build['parent_revision'],
        'images': {name: value['config_digest'] for name, value in fixture.build['images'].items()},
        'target_contracts': data_contracts(REPO), 'sources': [{'release': original['release'],
            'manifest_sha256': hashlib.sha256(raw).hexdigest(), 'control_digest': original['control']['config_digest'],
            'contracts': {name: original['data_compatibility'][name]['contract'] for name in ('bench', 'gateway')},
            'checks': {name: True for name in ('upgrade', 'candidate_read_write', 'previous_read_write', 'idempotent')}}]}


class SnapshotDeployment(updater_tests.FakeDeployment):
    """仅替代容器启动；快照、迁移故障和数据恢复执行真实 SQLite。"""

    def __init__(self, root: Path, data: Path) -> None:
        """创建合成业务双库。:param root: 更新根。:param data: 数据根。@return None。"""
        super().__init__()
        self.root, self.data = root, data
        for relative in ('bench/db.sqlite', 'gateway/gateway.sqlite'):
            path = data / relative
            path.parent.mkdir()
            with sqlite3.connect(path) as database:
                database.execute('CREATE TABLE synthetic_record(value TEXT)')
                database.execute("INSERT INTO synthetic_record VALUES('before')")

    def snapshot_databases(self, operation, selected, save):
        """保存实际两库快照。:param operation: 操作。:param selected: 目标。:param save: 持久回调。@return None。"""
        self.calls.append('snapshot')
        folder = self.root / 'operations' / operation['operation_id']
        atomic_text(folder / 'before.env', 'synthetic-before')
        snapshot = create_snapshot(self.data, folder / 'database-snapshot', 'test', operation)
        operation['database_snapshot'] = {'state': 'verified', 'bytes': sum(value['size'] for value in snapshot['databases'].values()), 'completed_at': snapshot['completed_at']}
        save()

    def migrate_databases(self, operation, plan, save):
        """逐库修改合成数据并注入半批失败。:param operation: 操作。:param plan: 计划。:param save: 持久回调。@return None。"""
        self.calls.append('migrate')
        for name, filename in (('bench', 'db.sqlite'), ('gateway', 'gateway.sqlite')):
            with sqlite3.connect(self.data / name / filename) as database:
                database.execute("UPDATE synthetic_record SET value='candidate'")
            operation.setdefault('database_migrations', {})[name] = {'state': 'completed', 'target_version': 1}
            save()
            if self.fail == 'first_database':
                raise ValueError('合成第一库迁移后失败')

    def restore(self, operation, save):
        """按实际快照恢复数据。:param operation: 原操作。:param save: 持久回调。@return None。"""
        if operation.get('database_snapshot') and not operation.get('release_started'):
            restore_snapshot(self.data, self.root / 'operations' / operation['operation_id'] / 'database-snapshot', 'test', operation, save)
        super().restore(operation, save)

    def cleanup_database_snapshots(self, protected):
        """实际轮换快照。:param protected: 活动操作。@return 清理结果。"""
        return rotate_snapshots(self.root / 'operations', 'test', protected)

    def values(self) -> list[str]:
        """读取合成两库实际值。@return 两库记录。"""
        values = []
        for relative in ('bench/db.sqlite', 'gateway/gateway.sqlite'):
            with sqlite3.connect(self.data / relative) as database:
                values.append(database.execute('SELECT value FROM synthetic_record').fetchone()[0])
        return values


class SystemMigrationTests(unittest.TestCase):
    """从真实 v1 安装及签名 v2 目标执行安装和失败恢复。"""

    def setUp(self) -> None:
        """准备独立真实签名材料与双库。@return None。"""
        base = updater_tests.SystemUpdaterTests()
        base.setUp()
        self.addCleanup(base.doCleanups)
        self.fixture, self.root = base.fixture, base.root
        self.old = copy.deepcopy(base.old)
        self.old['data_compatibility']['bench'] = {'contract': 'e' * 64, 'rollback_compatible': ['e' * 64]}
        old_path = self.root / 'releases' / self.old['release'] / 'system-release.json'
        old_path.write_text(json.dumps(self.old))
        old_path.with_suffix('.sig').unlink()
        sign_file(old_path, self.fixture.key)
        state = json.loads((self.root / 'state.json').read_text())
        state['current']['release'] = self.old
        self.fixture.build['release'] = 'ci-125-1'
        for name, image in self.fixture.build['images'].items():
            image['reference'] = f'ghcr.io/silentflower/vibebench-v3-{name}:v3-ci-125-1'
        self.fixture.manifest.write_text(json.dumps(self.fixture.build))
        self.evidence = self.fixture.root / 'migration-evidence.json'
        self.evidence.write_text(json.dumps(evidence_for(self.fixture, self.old, old_path.read_bytes())))
        self.target = create_release(self.fixture.manifest, self.fixture.policy, self.root / 'releases/system-ci-125-1',
            self.fixture.key, [12, 1], '合成迁移发行', migration_evidence=self.evidence)
        state['catalog'] = create_index(self.root / 'releases/system-ci-125-1/system-release.json', None,
            self.fixture.root / 'migration-index.json', self.fixture.key)
        atomic_json(self.root / 'state.json', state)
        self.policy = {**base.policy, 'schema_version': 2}
        self.backend = SnapshotDeployment(self.root, Path(self.policy['data_root']))
        self.engine = SystemUpdater(self.policy, self.backend)

    def request(self) -> dict:
        """冻结当前安装请求。@return 请求。"""
        raw = (self.root / 'releases/system-ci-125-1/system-release.json').read_bytes()
        return {'operation_id': str(uuid.uuid4()), 'expected_revision': self.engine.status()['revision'],
            'target_release': self.target['release'], 'target_manifest_sha256': hashlib.sha256(raw).hexdigest(), 'drain_timeout_seconds': 60}

    def finish(self) -> dict:
        """等候有限离线更新执行。@return 实际状态。"""
        self.engine.worker.join(10)
        self.assertFalse(self.engine.worker.is_alive())
        return self.engine.status()

    def test_actual_pair_snapshot_precedes_migration_and_commit(self) -> None:
        """两库快照先于迁移与切换，成功后有持久开放边界。@return None。"""
        self.engine.submit('install', self.request())
        status = self.finish()
        self.assertEqual(status['operation']['phase'], 'succeeded')
        self.assertEqual(self.backend.values(), ['candidate', 'candidate'])
        self.assertLess(self.backend.calls.index('snapshot'), self.backend.calls.index('migrate'))
        self.assertLess(self.backend.calls.index('migrate'), self.backend.calls.index('switch'))
        operation = self.engine._operation(status['operation']['operation_id'])
        self.assertTrue(operation['release_started'])
        self.assertEqual(status['operation']['database_snapshot']['state'], 'verified')

    def test_same_contract_ignores_changed_historical_allowlist(self) -> None:
        """普通业务发行保持数据合同，历史许可列表轮换不造成误拦。@return None。"""
        original = copy.deepcopy(self.target)
        for entry in original['data_compatibility'].values():
            entry['rollback_compatible'] = [entry['contract']]
        self.engine._migration_path({'release': original}, self.target)

    def test_partial_migration_restores_both_original_databases(self) -> None:
        """第一库完成后失败恢复同一组原数据与原版安装。@return None。"""
        self.backend.fail = 'first_database'
        self.engine.submit('install', self.request())
        status = self.finish()
        self.assertEqual(status['operation']['phase'], 'restored')
        self.assertEqual(status['current_release'], self.old['release'])
        self.assertEqual(self.backend.values(), ['before', 'before'])

    def test_candidate_health_failure_restores_actual_pair(self) -> None:
        """候选健康失败恢复两库，不留下半升级数据。@return None。"""
        self.backend.fail = 'health'
        self.engine.submit('install', self.request())
        self.assertEqual(self.finish()['operation']['phase'], 'restored')
        self.assertEqual(self.backend.values(), ['before', 'before'])

    def test_corrupt_asset_blocks_before_business_switch(self) -> None:
        """已缓存签名的迁移资产变更仍受摘要校验保护。@return None。"""
        path = self.root / 'releases/system-ci-125-1/database-migrations.json'
        path.write_bytes(path.read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, '迁移附件'):
            self.engine.submit('install', self.request())
        self.assertEqual(self.backend.calls, [])

    def test_wrong_source_proof_cannot_authorize_current_installation(self) -> None:
        """相同目标声明不能代替当前来源的真实演练。@return None。"""
        original = copy.deepcopy(self.engine.state['current'])
        original['selection']['control']['config_digest'] = 'sha256:' + 'f' * 64
        with self.assertRaisesRegex(ValueError, '来源版本'):
            self.engine._migration_path(original, self.target)

    def test_false_evidence_and_unknown_protocol_rejected(self) -> None:
        """任一验收断言未通过都不能生成可安装 v2。@return None。"""
        value = json.loads(self.evidence.read_text())
        value['sources'][0]['checks']['previous_read_write'] = False
        self.evidence.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, '演练未通过'):
            create_release(self.fixture.manifest, self.fixture.policy, self.fixture.root / 'invalid', self.fixture.key,
                [13, 1], '合成失败', migration_evidence=self.evidence)
        release = copy.deepcopy(self.target)
        release['compatibility']['updater'] = 1
        with self.assertRaises(ValueError):
            validate_release(release)


if __name__ == '__main__':
    unittest.main()
