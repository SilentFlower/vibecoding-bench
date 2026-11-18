"""迁移私有导出、目标暂存和重复导入的持久文件边界测试。"""
from __future__ import annotations

import shutil
import json
import tempfile
import unittest
from pathlib import Path

from cluster_archive import ArchiveIdentity
from cluster_migration_files import ImportStage, MigrationFiles
from runtime_files import atomic_json


class MigrationFileTests(unittest.TestCase):
    """采用真实文件与合成资料，发布前的副本可以按原包恢复。"""

    def setUp(self) -> None:
        """建立互相独立的源与目标节点根。:return: None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source_data, self.target_data = self.root / 'source', self.root / 'target'
        self.source = MigrationFiles(self.source_data, 'local', 'synthetic')
        self.target = MigrationFiles(self.target_data, 'b' * 32, 'synthetic')
        self.identity = ArchiveIdentity(operation_id='c' * 32, deployment_id='synthetic', source_node_key='local',
            account_id=1, environment_id='e' * 32, assignment_revision=3)
        self.environment = self.source_data / 'environments' / self.identity.environment_id
        atomic_json(self.environment / 'home/.claude.json', {'userID': 'a' * 64})
        atomic_json(self.environment / 'runtime/node-fence.json', {'phase': 'fenced'})
        atomic_json(self.environment / 'runtime/sender/sender.json', {'secret': 'synthetic-old-binding'})
        self.descriptor = self.source.export(self.environment, self.identity, 'd' * 32)
        self.request = ImportStage(node_key='b' * 32, transfer_id='f' * 32, target_revision=4, archive=self.descriptor)
        self.stage = self.target_data / 'node-migrations' / self.identity.operation_id / 'imports' / self.request.transfer_id

    def upload(self) -> None:
        """把已核对源包放入目标操作私有目录。:return: None。"""
        self.target.stage(self.request)
        source = self.source_data / 'node-migrations' / self.identity.operation_id / 'exports' / ('d' * 32 + '.tar')
        shutil.copyfile(source, self.stage / 'environment.tar')
        (self.stage / 'environment.tar').chmod(0o600)

    def test_export_receipt_is_idempotent_and_old_runtime_binding_is_excluded(self) -> None:
        """相同源导出回执可重读，导入保留逻辑资料并重建旧运行配置。:return: None。"""
        self.assertEqual(self.descriptor, self.source.export(self.environment, self.identity, 'd' * 32))
        self.upload()
        result = self.target.restore(self.request)
        self.assertEqual('verified', result['phase'])
        imported = self.stage / 'environment'
        self.assertEqual((self.environment / 'home/.claude.json').read_bytes(), (imported / 'home/.claude.json').read_bytes())
        self.assertFalse((imported / 'runtime/node-fence.json').exists())
        self.assertFalse((imported / 'runtime/sender').exists())
        self.assertEqual('fenced', json.loads((self.environment / 'runtime/node-fence.json').read_text())['phase'])

    def test_node_owner_receipt_stays_at_source_and_pending_handoff_refuses_export(self) -> None:
        """目标不继承旧Node交接身份，未发布交接继续保留源资料。:return: None。"""
        marker=self.environment/'runtime/owner-transition.json'
        atomic_json(marker,{'phase':'preparing'})
        with self.assertRaises(ValueError):
            self.source.export(self.environment,self.identity,'1'*32)
        atomic_json(marker,{'phase':'published'})
        descriptor=self.source.export(self.environment,self.identity,'2'*32)
        request=self.request.model_copy(update={'transfer_id':'3'*32,'archive':descriptor})
        self.target.stage(request)
        stage=self.target_data/'node-migrations'/self.identity.operation_id/'imports'/request.transfer_id
        shutil.copyfile(self.source_data/'node-migrations'/self.identity.operation_id/'exports'/('2'*32+'.tar'),stage/'environment.tar')
        (stage/'environment.tar').chmod(0o600)
        self.target.restore(request)
        self.assertFalse((stage/'environment/runtime/owner-transition.json').exists())
        self.assertTrue(marker.exists())

    def test_partial_upload_is_preserved_and_requires_new_transfer(self) -> None:
        """未知的部分上传不被后续stage覆盖，原字节保留供核对。:return: None。"""
        self.assertFalse(self.target.stage(self.request)['uploaded'])
        bundle = self.stage / 'environment.tar'
        bundle.write_bytes(b'partial')
        with self.assertRaisesRegex(ValueError, '不完整上传'):
            self.target.stage(self.request)
        self.assertEqual(b'partial', bundle.read_bytes())

    def test_unpublished_import_can_be_rebuilt_but_publish_intent_blocks_it(self) -> None:
        """私有未发布树可从同一包重建，开始发布后转为原阶段核对。:return: None。"""
        self.upload()
        self.target.restore(self.request)
        (self.stage / 'environment/home/.claude.json').write_text('临时未发布副本')
        self.target.restore(self.request)
        self.assertEqual((self.environment / 'home/.claude.json').read_bytes(),
            (self.stage / 'environment/home/.claude.json').read_bytes())
        atomic_json(self.stage / 'publish-intent.json', {'operation_id': self.identity.operation_id})
        with self.assertRaisesRegex(ValueError, '已开始发布'):
            self.target.restore(self.request)

    def test_broken_publish_intent_keeps_existing_private_tree(self) -> None:
        """损坏的发布意图保留原树，恢复不因链接断开而重建资料。:return: None。"""
        self.upload()
        self.target.restore(self.request)
        marker = self.stage / 'publish-intent.json'
        marker.symlink_to(self.stage / 'missing-intent')
        sentinel = self.stage / 'environment/home/.claude.json'
        sentinel.write_text('保留待核对的资料')
        with self.assertRaises((ValueError, OSError)):
            self.target.restore(self.request)
        self.assertEqual('保留待核对的资料', sentinel.read_text())

    def test_stage_rejects_other_node_and_assignment_revision(self) -> None:
        """目标节点及分配版本只能使用原冻结范围。:return: None。"""
        for change in ({'node_key': 'a' * 32}, {'target_revision': 5}):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, '版本'):
                self.target.stage(self.request.model_copy(update=change))

    def test_unknown_operation_directory_is_preserved(self) -> None:
        """未知目录保持资料与权限，缺少操作身份时拒绝接管。:return: None。"""
        operation = self.target_data / 'node-migrations' / self.identity.operation_id
        operation.mkdir(parents=True, mode=0o755)
        (operation / 'sentinel').write_text('未知资料')
        with self.assertRaisesRegex(ValueError, '权限|未核对'):
            self.target.stage(self.request)
        self.assertEqual('未知资料', (operation / 'sentinel').read_text())
        self.assertEqual(0o755, operation.stat().st_mode & 0o777)
