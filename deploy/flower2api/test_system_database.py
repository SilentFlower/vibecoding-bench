"""真实双库/WAL 的快照、故障恢复和精确保留验收。"""
import copy
import json
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from system_update_database import DATABASES, create_snapshot, restore_snapshot, rotate_snapshots, verify_snapshot
from runtime_files import atomic_json


class DatabaseSnapshotTests(unittest.TestCase):
    """验证实际数据库内容及中断边界，全部使用合成数据。"""

    def setUp(self) -> None:
        """创建独立部署与合成双库。@return None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.operations = self.root / 'updates/operations'
        self.operations.mkdir(parents=True)
        self.connections = []
        for relative in DATABASES.values():
            path = self.root / relative
            path.parent.mkdir()
            database = sqlite3.connect(path)
            database.execute('PRAGMA journal_mode=WAL')
            database.execute('CREATE TABLE records(id INTEGER PRIMARY KEY, value TEXT NOT NULL)')
            database.execute('INSERT INTO records VALUES(1,?)', ('synthetic-before',))
            database.commit()
            self.connections.append(database)
            self.addCleanup(database.close)
        self.operation = self.operation_record()
        self.folder = self.operations / self.operation['operation_id'] / 'database-snapshot'

    def operation_record(self) -> dict:
        """返回新的冻结操作。@return 合成操作。"""
        return {'operation_id': str(uuid.uuid4()), 'epoch': str(uuid.uuid4()), 'phase': 'succeeded',
            'original': {'release': {'release': 'system-ci-1-1'}}}

    def snapshot(self) -> dict:
        """保存并核验实际双库快照。@return 完整清单。"""
        self.folder.parent.mkdir(exist_ok=True)
        atomic_json(self.folder.parent / 'operation.json', self.operation)
        return create_snapshot(self.root, self.folder, 'synthetic', self.operation)

    def change(self, text: str) -> None:
        """修改模拟候选程序的数据。:param text: 合成值。@return None。"""
        for relative in DATABASES.values():
            with sqlite3.connect(self.root / relative) as database:
                database.execute('UPDATE records SET value=?', (text,))

    def values(self) -> list[str]:
        """读取两库实际记录。@return 合成值。"""
        values = []
        for relative in DATABASES.values():
            database = sqlite3.connect(self.root / relative)
            try:
                values.append(database.execute('SELECT value FROM records WHERE id=1').fetchone()[0])
            finally:
                database.close()
        return values

    def test_wal_commits_snapshot_and_restore_exact_data(self) -> None:
        """WAL 内已提交数据进入快照，失败恢复两库一致。@return None。"""
        snapshot = self.snapshot()
        self.assertEqual(set(snapshot['databases']), {'bench', 'gateway'})
        for database in self.connections:
            database.close()
        self.change('synthetic-candidate')
        restore_snapshot(self.root, self.folder, 'synthetic', self.operation, lambda: None)
        self.assertEqual(self.values(), ['synthetic-before', 'synthetic-before'])
        self.assertEqual({value['state'] for value in self.operation['database_restore'].values()}, {'completed'})

    def test_partial_restore_resumes_same_pair(self) -> None:
        """第一库替换后中断可继续恢复同一组。@return None。"""
        self.snapshot()
        for database in self.connections:
            database.close()
        self.change('synthetic-candidate')
        saved = []
        def save():
            saved.append(copy.deepcopy(self.operation))
            if self.operation['database_restore'].get('bench', {}).get('state') == 'completed':
                raise RuntimeError('synthetic-interruption')
        with self.assertRaisesRegex(RuntimeError, 'synthetic-interruption'):
            restore_snapshot(self.root, self.folder, 'synthetic', self.operation, save)
        self.operation = saved[-1]
        restore_snapshot(self.root, self.folder, 'synthetic', self.operation, lambda: None)
        self.assertEqual(self.values(), ['synthetic-before', 'synthetic-before'])

    def test_interrupted_temporary_copy_is_rebuilt(self) -> None:
        """恢复暂存复制中断后由同一持久意图续接。@return None。"""
        self.snapshot()
        for database in self.connections:
            database.close()
        self.change('synthetic-candidate')
        def partial(source, output):
            output.write(source.read(32))
            raise RuntimeError('synthetic-copy-interruption')
        with patch('system_update_database.shutil.copyfileobj', partial), self.assertRaisesRegex(RuntimeError, 'copy-interruption'):
            restore_snapshot(self.root, self.folder, 'synthetic', self.operation, lambda: None)
        restore_snapshot(self.root, self.folder, 'synthetic', self.operation, lambda: None)
        self.assertEqual(self.values(), ['synthetic-before', 'synthetic-before'])

    def test_admitted_business_data_never_replaced(self) -> None:
        """开放准入后的合法新写入保持。@return None。"""
        self.snapshot()
        self.change('synthetic-later-business')
        self.operation['release_started'] = True
        with self.assertRaisesRegex(ValueError, '后来数据'):
            restore_snapshot(self.root, self.folder, 'synthetic', self.operation, lambda: None)
        self.assertEqual(self.values(), ['synthetic-later-business', 'synthetic-later-business'])

    def test_completed_snapshot_still_requires_private_directory(self) -> None:
        """完成标记保持目录权限约束。@return None。"""
        self.snapshot()
        self.folder.chmod(0o755)
        with self.assertRaisesRegex(ValueError, '当前用户私有'):
            verify_snapshot(self.folder, 'synthetic', self.operation)

    def test_corrupt_one_snapshot_rejects_whole_restore(self) -> None:
        """一库快照损坏阻止整组恢复，当前数据保持。@return None。"""
        self.snapshot()
        self.change('synthetic-candidate')
        with (self.folder / 'gateway.sqlite').open('ab') as output:
            output.write(b'synthetic-corruption')
        with self.assertRaisesRegex(ValueError, '字节校验'):
            restore_snapshot(self.root, self.folder, 'synthetic', self.operation, lambda: None)
        self.assertEqual(self.values(), ['synthetic-candidate', 'synthetic-candidate'])

    def test_wrong_epoch_or_link_rejected(self) -> None:
        """外来代次和链接路径不作为恢复来源。@return None。"""
        self.snapshot()
        changed = {**self.operation, 'epoch': str(uuid.uuid4())}
        with self.assertRaisesRegex(ValueError, '归属'):
            verify_snapshot(self.folder, 'synthetic', changed)
        path = self.folder / 'bench.sqlite'
        path.unlink()
        path.symlink_to(self.root / 'bench/db.sqlite')
        with self.assertRaisesRegex(ValueError, '普通文件'):
            verify_snapshot(self.folder, 'synthetic', self.operation)

    def test_space_failure_preserves_original_without_incomplete_manifest(self) -> None:
        """空间不足在快照及迁移之前受控退出。@return None。"""
        self.folder.parent.mkdir()
        with patch('system_update_database.shutil.disk_usage') as usage:
            usage.return_value.free = 0
            with self.assertRaisesRegex(ValueError, '空间不足'):
                create_snapshot(self.root, self.folder, 'synthetic', self.operation)
        self.assertFalse((self.folder / 'manifest.json').exists())
        self.assertEqual(self.values(), ['synthetic-before', 'synthetic-before'])

    def test_rotation_keeps_two_and_active_dependency(self) -> None:
        """保留两组完成快照及活动引用，外来目录保持。@return None。"""
        identifiers = []
        for index in range(4):
            self.operation = self.operation_record()
            identifiers.append(self.operation['operation_id'])
            self.folder = self.operations / self.operation['operation_id'] / 'database-snapshot'
            self.snapshot()
            path = self.folder / 'manifest.json'
            value = json.loads(path.read_text())
            value['completed_at'] = f'2026-11-12T00:00:0{index}Z'
            atomic_json(path, value)
        external = self.operations / 'external'
        external.mkdir()
        result = rotate_snapshots(self.operations, 'synthetic', {identifiers[0]})
        self.assertEqual(result['removed_operations'], [identifiers[1]])
        self.assertTrue(external.is_dir())
        self.assertEqual(result['retained_groups'], 3)


if __name__ == '__main__':
    unittest.main()
