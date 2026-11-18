"""节点源码快照、固定原scope及中央内容对象导入的真实文件测试。"""
from __future__ import annotations

import hashlib
import io
import json
import tarfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cluster_workspace import NodeWorkspaceSnapshots, WorkspaceSnapshotArchive, WorkspaceSnapshotReference, WorkspaceSnapshotRequest, read_workspace_bundle, write_workspace_bundle
from project_library import materialize_snapshot, snapshot_tree
import test_cluster_terminal as terminal_fixture


class WorkspaceSnapshotTests(unittest.TestCase):
    """复用原节点持久终端和证明，源码及tar均由真实文件系统承载。"""

    def setUp(self) -> None:
        """建立已启动节点工作和可核对的实际账号源码目录。:return: None。"""
        fixture = terminal_fixture.NodeTerminalTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture, self.scope, self.data = fixture, fixture.scope, fixture.fixture.root
        fixture.terminals.start(fixture.request)
        self.workspace = self.data / 'environments' / self.scope.environment_id / 'projects/synthetic'
        self.workspace.mkdir(parents=True)
        (self.workspace / 'app.py').write_text('VALUE = "合成源码"\n')
        (self.workspace / 'empty.txt').touch()
        fixture.terminal.workspace.return_value = self.workspace
        job = {'account': {'id': 1}, 'source': self.scope.source,
            'row': {'environment_id': self.scope.environment_id, 'generation': self.scope.generation}}
        fixture.host.runtime.job_for_container = Mock(return_value=job)
        fixture.host.runtime.control_execution = Mock(return_value={'exists': True, 'source': self.scope.source, 'frozen': True})
        self.snapshots = NodeWorkspaceSnapshots(fixture.terminals)
        self.snapshot_id = '7' * 32

    def request(self, purpose='candidate') -> WorkspaceSnapshotRequest:
        """构造原scope快照。:param purpose: 原用途。:return: 固定请求。"""
        return WorkspaceSnapshotRequest(scope=self.scope, snapshot_id=self.snapshot_id, purpose=purpose)

    def archive(self, purpose='candidate'):
        """创建实际有界包。:param purpose: 原用途。:return: 包路径及冻结回执。"""
        receipt = WorkspaceSnapshotArchive.model_validate(self.snapshots.create(self.request(purpose)))
        path = self.snapshots._parent(self.scope) / (self.snapshot_id + '.tar')
        return path, receipt

    def test_shared_writer_rejects_changed_objects_and_preserves_published_package(self) -> None:
        """双向共用打包器核对真实对象，发布后的原包保持固定。:return: None。"""
        objects=self.data/'writer-objects'
        manifest=snapshot_tree(self.workspace,objects)
        request=self.request()
        path=self.data/'writer-transfer/snapshot.tar'
        receipt=write_workspace_bundle(path,request,manifest,objects)
        self.assertEqual(manifest,read_workspace_bundle(path,receipt))
        previous=path.read_bytes()
        with self.assertRaises(FileExistsError):
            write_workspace_bundle(path,request,manifest,objects)
        self.assertEqual(previous,path.read_bytes())
        item=next(item for item in manifest['files'].values() if item['size'])
        (objects/item['digest'][:2]/item['digest']).write_bytes(b'x'*item['size'])
        other=path.with_name('damaged.tar')
        with self.assertRaisesRegex(ValueError,'对象在打包前发生变化'):
            write_workspace_bundle(other,request,manifest,objects)
        self.assertFalse(other.exists())
        self.assertFalse(other.with_name('.damaged.tar.tmp').exists())

    def test_candidate_freezes_original_process_and_materializes_same_content(self) -> None:
        """候选按原scope冻结，中央导入与原snapshot_tree逐文件一致。:return: None。"""
        path, receipt = self.archive()
        self.fixture.host.runtime.control_execution.assert_called_once_with('original-token', 'freeze')
        objects = self.data / 'central-objects'
        manifest = read_workspace_bundle(path, receipt, objects)
        self.assertEqual(snapshot_tree(self.workspace), manifest)
        destination = self.data / 'candidate'
        materialize_snapshot(manifest, objects, destination)
        self.assertEqual((self.workspace / 'app.py').read_bytes(), (destination / 'app.py').read_bytes())
        self.assertEqual(manifest, snapshot_tree(destination))
        self.assertEqual(receipt.model_dump(), self.snapshots.create(self.request()))
        self.assertEqual(receipt.model_dump(), self.snapshots.get(WorkspaceSnapshotReference(scope=self.scope, snapshot_id=self.snapshot_id)))
        self.fixture.host.runtime.control_execution.assert_called_once()

    def test_baseline_is_manifest_only_and_cannot_be_rebased_after_input(self) -> None:
        """首次基线只传清单，输入后同快照查询保持原值，新基线被拒绝。:return: None。"""
        path, receipt = self.archive('baseline')
        self.assertEqual(snapshot_tree(self.workspace), read_workspace_bundle(path, receipt))
        self.fixture.host.runtime.control_execution.assert_not_called()
        self.fixture.terminals.send(self.fixture.input())
        self.assertEqual(receipt.model_dump(), self.snapshots.create(self.request('baseline')))
        with self.assertRaisesRegex(ValueError, '首次输入'):
            self.snapshots.create(self.request('baseline').model_copy(update={'snapshot_id': '8' * 32}))

    def test_wrong_scope_unfrozen_process_link_and_disk_shortage_preserve_originals(self) -> None:
        """错范围、冻结缺失、链接及磁盘不足均阻止有效包发布。:return: None。"""
        self.fixture.host.runtime.control_execution.return_value = {'source': self.scope.source, 'frozen': False}
        with self.assertRaisesRegex(ValueError, '冻结'):
            self.snapshots.create(self.request())
        self.fixture.host.runtime.control_execution.return_value = {'source': self.scope.source, 'frozen': True}
        with patch('cluster_workspace.shutil.disk_usage', return_value=SimpleNamespace(free=0)):
            with self.assertRaisesRegex(ValueError, '磁盘'):
                self.snapshots.create(self.request())
        self.assertFalse((self.snapshots._parent(self.scope) / (self.snapshot_id + '.tar')).exists())
        self.assertEqual('VALUE = "合成源码"\n', (self.workspace / 'app.py').read_text())
        outside = self.data / 'outside.txt'
        outside.write_text('原外部文件')
        (self.workspace / 'linked.txt').symlink_to(outside)
        with self.assertRaises((OSError, ValueError)):
            self.snapshots.create(self.request().model_copy(update={'snapshot_id': '8' * 32}))
        self.assertEqual('原外部文件', outside.read_text())
        with self.assertRaises(ValueError):
            self.snapshots.get(WorkspaceSnapshotReference(scope=self.scope.model_copy(update={'account_id': 2}), snapshot_id=self.snapshot_id))

    def rewritten(self, path, receipt, entries, *, tail=b''):
        """生成身份仍有界的恶意包夹具。:param path: 原包。:param receipt: 原身份。:param entries: 新条目。:param tail: 尾随字节。:return: 新路径和新整包摘要回执。"""
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode='w') as archive:
            for member, raw in entries:
                archive.addfile(member, io.BytesIO(raw) if member.isfile() else None)
        data = output.getvalue() + tail
        target = self.data / ('modified-' + str(len(list(self.data.glob('modified-*')))) + '.tar')
        target.write_bytes(data)
        target.chmod(0o600)
        return target, receipt.model_copy(update={'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)})

    def test_bundle_rejects_extra_link_missing_object_and_nonzero_tail_before_publish(self) -> None:
        """未知成员及链接、缺对象和拼接尾部均被拒绝，中央对象保持未发布。:return: None。"""
        path, receipt = self.archive()
        with tarfile.open(path, 'r') as archive:
            entries = [(member, archive.extractfile(member).read()) for member in archive]
        link = tarfile.TarInfo('objects/aa/' + 'a' * 64)
        link.type, link.linkname = tarfile.SYMTYPE, '/outside'
        for selected, tail in (([entries[0]], b''), (entries + [(link, b'')], b''),
                (entries + [entries[-1]], b''), (entries, b'undeclared-tail')):
            with self.subTest(count=len(selected), tail=tail):
                modified, identity = self.rewritten(path, receipt, selected, tail=tail)
                objects = self.data / 'rejected-objects'
                with self.assertRaises(ValueError):
                    read_workspace_bundle(modified, identity, objects)
                self.assertFalse(objects.exists())

    def test_corrupt_existing_object_is_preserved_and_wrong_envelope_scope_is_rejected(self) -> None:
        """坏对象保留供核对，清单换scope不进入中央对象写入。:return: None。"""
        path, receipt = self.archive()
        objects = self.data / 'objects'
        manifest = snapshot_tree(self.workspace)
        digest = manifest['files']['app.py']['digest']
        destination = objects / digest[:2] / digest
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b'original-corrupt-data')
        destination.chmod(0o600)
        with self.assertRaisesRegex(ValueError, '已有源码对象'):
            read_workspace_bundle(path, receipt, objects)
        self.assertEqual(b'original-corrupt-data', destination.read_bytes())
        with tarfile.open(path, 'r') as archive:
            entries = [(member, archive.extractfile(member).read()) for member in archive]
        envelope = json.loads(entries[0][1])
        envelope['scope']['account_id'] = 2
        raw = json.dumps(envelope).encode()
        first = tarfile.TarInfo('snapshot.json')
        first.size = len(raw)
        modified, identity = self.rewritten(path, receipt, [(first, raw), *entries[1:]])
        with self.assertRaisesRegex(ValueError, 'scope'):
            read_workspace_bundle(modified, identity)


if __name__ == '__main__':
    unittest.main()
