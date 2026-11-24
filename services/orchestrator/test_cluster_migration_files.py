"""迁移私有导出、目标暂存和重复导入的持久文件边界测试。"""
from __future__ import annotations

import shutil
import json
import tempfile
import unittest
import os
from pathlib import Path

from cli_scratchpad import SCRATCHPAD_RUNTIME, SCRATCHPAD_STORE
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

    def test_v2_durable_workspace_and_transcript_are_moved_without_host_secrets(self) -> None:
        """同环境工作和回放数据保持字节，发送配置及派生文件保留在源。:return: None。"""
        session = 'fa00fa00-fa00-4a00-8a00-fa00fa00fa00'
        project = '-native-tui-workspaces-' + 'a' * 64
        workspace = 'runtime/native/tui-workspaces/'
        home = f'runtime/native/tui-sessions/{session}/home/'
        keep = [
            workspace + 'f' * 64 + '.json', workspace + 'a' * 64 + '/notes.txt',
            home + f'.claude/projects/{project}/{session}.jsonl', 'runtime/native/tui-v2-submissions.json',
        ]
        drop = [workspace + '.binding.pending', home + '.claude/.credentials.json',
            home + '.claude/.claude.json', home + 'tmp/session.sock',
            'runtime/native/tui-provider-backoff/previous', 'runtime/native/tui-v2-submissions.lock',
            'runtime/native/worker-profile/settings.json', 'runtime/sender/tui-local-provider.json']
        for index, path in enumerate(keep + drop):
            atomic_json(self.environment / path, {'synthetic': index})
        descriptor = self.source.export(self.environment, self.identity, '6' * 32)
        request = self.request.model_copy(update={'transfer_id': '7' * 32, 'archive': descriptor})
        self.target.stage(request)
        stage = self.stage.parent / request.transfer_id
        bundle = self.source_data / 'node-migrations' / self.identity.operation_id / 'exports' / ('6' * 32 + '.tar')
        shutil.copyfile(bundle, stage/'environment.tar')
        (stage/'environment.tar').chmod(0o600)
        self.assertEqual('verified', self.target.restore(request)['phase'])
        for path in keep:
            self.assertEqual((self.environment/path).read_bytes(), (stage/'environment'/path).read_bytes())
        for path in drop:
            self.assertFalse((stage/'environment'/path).exists())
            self.assertTrue((self.environment/path).exists())

        secret = self.source_data/'unrelated-secret'
        secret.write_text('synthetic')
        os.link(secret, self.environment / workspace / ('a' * 64) / 'linked')
        with self.assertRaisesRegex(ValueError, '硬链接'):
            self.source.export(self.environment, self.identity, '8' * 32)

    def test_partial_upload_is_preserved_and_requires_new_transfer(self) -> None:
        """未知的部分上传不被后续stage覆盖，原字节保留供核对。:return: None。"""
        self.assertFalse(self.target.stage(self.request)['uploaded'])
        bundle = self.stage / 'environment.tar'
        bundle.write_bytes(b'partial')
        self.assertEqual('incomplete', self.target.stage(self.request)['upload_state'])
        self.assertEqual(b'partial', bundle.read_bytes())

    def test_partial_upload_cannot_replace_verified_data_or_follow_links(self) -> None:
        """已核验包变化和暂存链接保留为错误，不能作为普通中断换源。:return: None。"""
        self.target.stage(self.request)
        bundle = self.stage / 'environment.tar'
        bundle.write_bytes(b'partial')
        atomic_json(self.stage / 'verified.json', {'phase': 'verified'})
        with self.assertRaisesRegex(ValueError, '已核验'):
            self.target.stage(self.request)
        (self.stage / 'verified.json').unlink()
        bundle.unlink()
        bundle.symlink_to(self.source_data / 'outside')
        with self.assertRaisesRegex(ValueError, '普通文件'):
            self.target.stage(self.request)

    def test_registered_scratchpad_mount_is_rebuilt_and_session_data_is_preserved(self) -> None:
        """登记挂载工作目录由目标重建，真实会话和源目录保持完整。:return: None。"""
        transient = self.environment / SCRATCHPAD_RUNTIME
        for name in ('lower', 'work'):
            (transient / name).mkdir(parents=True, mode=0o700)
        transient.chmod(0o700)
        marker = {'protocol': 1, 'environment_id': self.identity.environment_id}
        atomic_json(transient / 'mount.json', marker)
        atomic_json(self.environment / SCRATCHPAD_STORE / 'layout.json', marker)
        session = self.environment / SCRATCHPAD_STORE / 'data/session/marker'
        session.parent.mkdir(parents=True, mode=0o700)
        session.write_bytes(b'synthetic-session')
        session.chmod(0o640)
        session.with_name('link').symlink_to('marker')
        descriptor = self.source.export(self.environment, self.identity, '1' * 32)
        self.request = self.request.model_copy(update={'archive': descriptor})
        self.target.stage(self.request)
        source = self.source_data / 'node-migrations' / self.identity.operation_id / 'exports' / ('1' * 32 + '.tar')
        shutil.copyfile(source, self.stage / 'environment.tar')
        (self.stage / 'environment.tar').chmod(0o600)
        self.target.restore(self.request)
        imported = self.stage / 'environment'
        restored = imported / SCRATCHPAD_STORE / 'data/session/marker'
        self.assertEqual(session.read_bytes(), restored.read_bytes())
        self.assertEqual(0o640, restored.stat().st_mode & 0o777)
        self.assertEqual('marker', str(restored.with_name('link').readlink()))
        self.assertFalse((imported / SCRATCHPAD_RUNTIME).exists())
        self.assertTrue((transient / 'mount.json').exists())

    def test_unknown_scratchpad_mount_directory_is_preserved_in_migration(self) -> None:
        """未登记的同名目录保全到目标，避免历史文件被目录名称排除。:return: None。"""
        marker = self.environment / SCRATCHPAD_RUNTIME / 'historical.json'
        atomic_json(marker, {'session': 'synthetic-history'})
        descriptor = self.source.export(self.environment, self.identity, '1' * 32)
        self.request = self.request.model_copy(update={'archive': descriptor})
        self.target.stage(self.request)
        source = self.source_data / 'node-migrations' / self.identity.operation_id / 'exports' / ('1' * 32 + '.tar')
        shutil.copyfile(source, self.stage / 'environment.tar')
        (self.stage / 'environment.tar').chmod(0o600)
        self.target.restore(self.request)
        self.assertEqual(marker.read_bytes(), (self.stage / 'environment' / SCRATCHPAD_RUNTIME / 'historical.json').read_bytes())

    def test_foreign_scratchpad_registration_blocks_export_and_preserves_source(self) -> None:
        """外来挂载登记阻挡迁移导出并保留源资料。:return: None。"""
        marker = self.environment / SCRATCHPAD_RUNTIME / 'mount.json'
        atomic_json(marker, {'protocol': 1, 'environment_id': 'a' * 32})
        before = marker.read_bytes()
        with self.assertRaisesRegex(ValueError, '归属或协议'):
            self.source.export(self.environment, self.identity, '1' * 32)
        self.assertEqual(before, marker.read_bytes())
        self.assertFalse((self.source_data / 'node-migrations' / self.identity.operation_id / 'exports' / ('1' * 32 + '.tar')).exists())

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
