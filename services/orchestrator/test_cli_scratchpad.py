"""CLI临时文件保全、挂载归属及失败恢复的离线测试。"""
import io
import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from docker.errors import NotFound

from cli_scratchpad import (SCRATCHPAD_RUNTIME, SCRATCHPAD_STORE, SCRATCHPAD_TARGET,
    prepare_scratchpad_mount, preserve_cli_scratchpad, remove_scratchpad_volume, restore_cli_scratchpad,
    scratchpad_runtime_registered)
from runtime_files import atomic_json
from storage_backup import create_backup_data, verify_backup_data
from storage_maintenance import tree_inventory


class CliScratchpadTests(unittest.TestCase):
    """使用真实文件与合成Docker替身验证生命周期边界。"""

    def setUp(self) -> None:
        """建立每例独立的账号环境和受控Docker卷。:return: None。"""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name)
        self.data = self.parent / 'bench'
        self.row = {'environment_id': 'a' * 32, 'generation': 3}
        self.root = self.data / 'environments' / self.row['environment_id']
        self.root.mkdir(parents=True, mode=0o700)
        (self.root / 'runtime/cli').mkdir(parents=True, mode=0o750)
        os.chown(self.root / 'runtime/cli', 0, 1000)
        self.client = Mock()
        supported = patch('cli_scratchpad._disk_supported', return_value=True)
        self.supported = supported.start()
        self.addCleanup(supported.stop)
        self.client.images.get.return_value.attrs = {'Config': {'Labels': {'vibebench.cli-scratchpad-protocol': '1'}}}
        self.volumes = {}

        def get_volume(name):
            if name not in self.volumes:
                raise NotFound('missing')
            return self.volumes[name]

        def create_volume(name, driver, driver_opts, labels):
            volume = SimpleNamespace(name=name, reload=Mock(), attrs={
                'Driver': driver, 'Options': driver_opts, 'Labels': labels})
            volume.remove = Mock(side_effect=lambda: self.volumes.pop(name))
            self.volumes[name] = volume
            return volume

        self.client.volumes.get.side_effect = get_volume
        self.client.volumes.create.side_effect = create_volume
        self.client.api.exec_create.return_value = {'Id': 'export-exec'}
        self.client.api.exec_start.side_effect = lambda *args, **kwargs: iter([self.archive()])
        self.client.api.exec_inspect.return_value = {'Running': False, 'ExitCode': 0}
        self.runtime = SimpleNamespace(client=self.client, data=self.data, host_data=self.data,
            deployment='test', node_key=None, image='synthetic', _root=lambda row: self.data / 'environments' / row['environment_id'])
        self.container = SimpleNamespace(id='old-cli', status='running', attrs={'Mounts': [], 'State': {'StartedAt': 'boot-one'}}, reload=Mock(),
            exec_run=Mock(return_value=SimpleNamespace(exit_code=0, output=b'')))

    @staticmethod
    def archive(extra: list[tuple[str, bytes, bytes, str]] | None = None) -> bytes:
        """构造包含多会话、权限和链接的真实tar。:param extra: 额外条目。:return: tar字节。"""
        output = io.BytesIO()
        rows = [('claude-1000', b'', tarfile.DIRTYPE, '')]
        for session in ('session-a', 'session-b', 'session-c'):
            rows.extend([(f'claude-1000/{session}', b'', tarfile.DIRTYPE, ''),
                (f'claude-1000/{session}/marker', session.encode(), tarfile.REGTYPE, '')])
        rows.extend([('claude-1000/session-a/link', b'', tarfile.SYMTYPE, 'marker'),
            ('claude-1000/session-a/hard', b'', tarfile.LNKTYPE, 'claude-1000/session-a/marker')])
        with tarfile.open(fileobj=output, mode='w') as archive:
            for name, content, kind, link in rows + (extra or []):
                member = tarfile.TarInfo(name)
                member.type, member.linkname = kind, link
                member.uid = member.gid = 1000
                member.mode = 0o700 if kind == tarfile.DIRTYPE else 0o777 if kind == tarfile.SYMTYPE else 0o640
                member.mtime = 1234567890
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content) if kind == tarfile.REGTYPE else None)
        return output.getvalue()

    def test_legacy_copy_restore_and_disk_mount_keep_paths_metadata_and_sessions(self) -> None:
        """旧CLI导出与原实例恢复后，新挂载保全三会话及链接。:return: None。"""
        preserve_cli_scratchpad(self.runtime, self.row, self.container)
        self.client.api.exec_create.assert_called_once()
        self.assertEqual('running', self.container.status)
        captured = []
        def restored(command, **kwargs):
            captured.append((self.root / 'runtime/cli' / Path(command[-1]).name).read_bytes())
            return SimpleNamespace(exit_code=0, output=b'')
        self.container.exec_run.side_effect = restored
        self.container.attrs['State']['StartedAt'] = 'boot-two'
        restore_cli_scratchpad(self.runtime, self.row, self.container)
        self.assertEqual([self.archive()], captured)
        mount = prepare_scratchpad_mount(self.runtime, self.row)
        self.assertEqual(SCRATCHPAD_TARGET, mount['Target'])
        self.assertTrue(mount['VolumeOptions']['NoCopy'])
        data = self.root / SCRATCHPAD_STORE / 'data'
        for session in ('session-a', 'session-b', 'session-c'):
            self.assertEqual(session, (data / session / 'marker').read_text())
        marker = data / 'session-a/marker'
        self.assertEqual(1000, marker.stat().st_uid)
        self.assertEqual(0o640, marker.stat().st_mode & 0o777)
        self.assertEqual(1234567890, marker.stat().st_mtime)
        self.assertEqual(marker.stat().st_ino, (data / 'session-a/hard').stat().st_ino)
        self.assertEqual('marker', os.readlink(data / 'session-a/link'))
        volume = self.volumes[mount['Source']]
        self.assertIn('noexec,nosuid,nodev', volume.attrs['Options']['o'])
        self.container.attrs['Mounts'] = [{'Destination': SCRATCHPAD_TARGET, 'Type': 'volume',
            'Name': volume.name, 'RW': True}]
        self.container.exec_run = Mock(return_value=SimpleNamespace(exit_code=0, output=b'{"safe":true,"uid":1000}'))
        restore_cli_scratchpad(self.runtime, self.row, self.container)
        preserve_cli_scratchpad(self.runtime, self.row, self.container)
        self.client.api.exec_create.assert_called_once()

    def test_copy_failure_retains_original(self) -> None:
        """导出流中断保留原实例及既有回执。:return: None。"""
        preserve_cli_scratchpad(self.runtime, self.row, self.container)
        previous = (self.root / SCRATCHPAD_STORE / 'legacy.json').read_bytes()

        def failing_stream():
            yield b'partial'
            raise OSError('synthetic')

        self.client.api.exec_start.side_effect = lambda *args, **kwargs: failing_stream()
        with self.assertRaises(OSError):
            preserve_cli_scratchpad(self.runtime, self.row, self.container)
        self.assertEqual(previous, (self.root / SCRATCHPAD_STORE / 'legacy.json').read_bytes())
        self.assertEqual('running', self.container.status)
        restore_cli_scratchpad(self.runtime, self.row, self.container)

    def test_disk_full_before_publication_keeps_source(self) -> None:
        """磁盘写入失败时原CLI继续持有全部数据。:return: None。"""
        with patch('cli_scratchpad.os.fsync', side_effect=OSError(28, 'synthetic')):
            with self.assertRaises(OSError):
                preserve_cli_scratchpad(self.runtime, self.row, self.container)
        self.assertEqual('running', self.container.status)
        self.assertFalse((self.root / SCRATCHPAD_STORE / 'legacy.json').exists())

    def test_export_failure_or_unknown_pause_blocks_publication(self) -> None:
        """导出进程失败和未知暂停均保留源实例并阻挡发布。:return: None。"""
        self.client.api.exec_inspect.return_value = {'Running': False, 'ExitCode': 1}
        with self.assertRaisesRegex(ValueError, '一致性'):
            preserve_cli_scratchpad(self.runtime, self.row, self.container)
        self.assertFalse((self.root / SCRATCHPAD_STORE / 'legacy.json').exists())
        self.client.api.exec_inspect.return_value = {'Running': False, 'ExitCode': 0}
        preserve_cli_scratchpad(self.runtime, self.row, self.container)
        self.assertEqual('running', self.container.status)
        self.container.status = 'paused'
        with self.assertRaisesRegex(ValueError, '源状态不明'):
            preserve_cli_scratchpad(self.runtime, self.row, self.container)

    def test_restore_failure_protects_last_snapshot_and_can_retry_same_boot(self) -> None:
        """恢复失败保护原转存包，同一启动代次重试成功后避免重复覆盖。:return: None。"""
        preserve_cli_scratchpad(self.runtime, self.row, self.container)
        previous = (self.root / SCRATCHPAD_STORE / 'legacy.json').read_bytes()
        self.container.attrs['State']['StartedAt'] = 'boot-two'
        self.container.exec_run.return_value = SimpleNamespace(exit_code=1, output=b'')
        with self.assertRaisesRegex(ValueError, '恢复未确认'):
            restore_cli_scratchpad(self.runtime, self.row, self.container)
        with self.assertRaisesRegex(ValueError, '恢复尚未确认'):
            preserve_cli_scratchpad(self.runtime, self.row, self.container)
        self.assertEqual(previous, (self.root / SCRATCHPAD_STORE / 'legacy.json').read_bytes())
        self.container.exec_run.return_value = SimpleNamespace(exit_code=0, output=b'')
        restore_cli_scratchpad(self.runtime, self.row, self.container)
        calls = self.container.exec_run.call_count
        restore_cli_scratchpad(self.runtime, self.row, self.container)
        self.assertEqual(calls, self.container.exec_run.call_count)

    def test_live_source_keeps_new_files_and_allows_next_preservation(self) -> None:
        """停止失败后仍在同次启动的源保留最新内容，下次转存正常发布。:return: None。"""
        preserve_cli_scratchpad(self.runtime, self.row, self.container)
        restore_cli_scratchpad(self.runtime, self.row, self.container)
        self.container.exec_run.assert_not_called()
        self.assertFalse((self.root / SCRATCHPAD_STORE / 'restore.json').exists())
        self.client.api.exec_start.side_effect = lambda *args, **kwargs: iter([self.archive([
            ('claude-1000/session-a/new-file', b'new-content', tarfile.REGTYPE, '')])])
        preserve_cli_scratchpad(self.runtime, self.row, self.container)
        prepare_scratchpad_mount(self.runtime, self.row)
        self.assertEqual('new-content', (self.root / SCRATCHPAD_STORE / 'data/session-a/new-file').read_text())

    def test_restart_during_export_keeps_previous_snapshot(self) -> None:
        """导出中源启动身份变化时保留已发布快照，禁止发布跨启动数据。:return: None。"""
        preserve_cli_scratchpad(self.runtime, self.row, self.container)
        previous = (self.root / SCRATCHPAD_STORE / 'legacy.json').read_bytes()
        def restart():
            self.container.attrs['State']['StartedAt'] = 'boot-two'
        self.client.api.exec_inspect.side_effect = lambda *args: (restart() or {'Running': False, 'ExitCode': 0})
        with self.assertRaisesRegex(ValueError, '启动身份变化'):
            preserve_cli_scratchpad(self.runtime, self.row, self.container)
        self.assertEqual(previous, (self.root / SCRATCHPAD_STORE / 'legacy.json').read_bytes())

    def test_missing_source_boot_blocks_export_and_old_receipt_restores_conservatively(self) -> None:
        """缺少源启动身份拒绝新转存，历史回执继续完整恢复核验。:return: None。"""
        self.container.attrs['State'] = {}
        with self.assertRaisesRegex(ValueError, '启动身份'):
            preserve_cli_scratchpad(self.runtime, self.row, self.container)
        self.client.api.exec_create.assert_not_called()
        self.container.attrs['State']['StartedAt'] = 'boot-one'
        preserve_cli_scratchpad(self.runtime, self.row, self.container)
        marker = self.root / SCRATCHPAD_STORE / 'legacy.json'
        receipt = json.loads(marker.read_text())
        receipt.pop('started_at')
        atomic_json(marker, receipt)
        with self.assertRaisesRegex(ValueError, '尚未恢复到本次启动'):
            preserve_cli_scratchpad(self.runtime, self.row, self.container)
        restore_cli_scratchpad(self.runtime, self.row, self.container)
        self.container.exec_run.assert_called_once()
        preserve_cli_scratchpad(self.runtime, self.row, self.container)

    def test_unrestored_restart_cannot_replace_last_snapshot(self) -> None:
        """重启后的空内存盘须先恢复原快照，避免新转存覆盖唯一旧副本。:return: None。"""
        preserve_cli_scratchpad(self.runtime, self.row, self.container)
        marker = self.root / SCRATCHPAD_STORE / 'legacy.json'
        before = marker.read_bytes()
        self.container.attrs['State']['StartedAt'] = 'boot-two'
        with self.assertRaisesRegex(ValueError, '尚未恢复到本次启动'):
            preserve_cli_scratchpad(self.runtime, self.row, self.container)
        self.assertEqual(before, marker.read_bytes())
        self.client.api.exec_create.assert_called_once()
        restore_cli_scratchpad(self.runtime, self.row, self.container)
        preserve_cli_scratchpad(self.runtime, self.row, self.container)
        self.assertEqual('boot-two', json.loads(marker.read_text())['started_at'])

    def test_tar_paths_and_types_are_rejected_before_publishing(self) -> None:
        """穿越、重复、链接父目录和设备条目均保护源文件。:return: None。"""
        for entry in [('claude-1000/../../escape', b'bad', tarfile.REGTYPE, ''),
                ('claude-1000/session-a/marker', b'bad', tarfile.REGTYPE, ''),
                ('claude-1000/session-a/link/child', b'bad', tarfile.REGTYPE, ''),
                ('claude-1000/device', b'', tarfile.CHRTYPE, '')]:
            with self.subTest(entry=entry[0]):
                self.client.api.exec_start.side_effect = lambda *args, entry=entry, **kwargs: iter([self.archive([entry])])
                with self.assertRaises(ValueError):
                    preserve_cli_scratchpad(self.runtime, self.row, self.container)
                self.assertEqual('running', self.container.status)
                self.assertFalse((self.root / SCRATCHPAD_STORE / 'legacy.json').exists())
        self.assertFalse((self.parent / 'escape').exists())

    def test_publish_interruption_recovers_verified_directory(self) -> None:
        """目录已发布而布局回执中断时，按原清单继续发布。:return: None。"""
        original = atomic_json

        def fail_layout(path, value):
            if path.name == 'layout.json':
                raise OSError('synthetic')
            original(path, value)

        with patch('cli_scratchpad.atomic_json', side_effect=fail_layout):
            with self.assertRaises(OSError):
                prepare_scratchpad_mount(self.runtime, self.row)
        prepare_scratchpad_mount(self.runtime, self.row)
        self.assertTrue((self.root / SCRATCHPAD_STORE / 'layout.json').is_file())

    def test_unsupported_environment_uses_tmpfs_and_rebinds_only_fresh_cli(self) -> None:
        """能力不足沿用tmpfs，新建角色显式接续同环境快照。:return: None。"""
        self.supported.return_value = False
        self.assertIsNone(prepare_scratchpad_mount(self.runtime, self.row))
        self.client.volumes.create.assert_not_called()
        preserve_cli_scratchpad(self.runtime, self.row, self.container)
        self.assertIsNone(prepare_scratchpad_mount(self.runtime, self.row))
        self.container.id = 'new-cli'
        restore_cli_scratchpad(self.runtime, self.row, self.container, fresh=True)
        receipt = json.loads((self.root / SCRATCHPAD_STORE / 'legacy.json').read_text())
        self.assertEqual('new-cli', receipt['container_id'])
        preserve_cli_scratchpad(self.runtime, self.row, self.container)
        self.assertEqual('running', self.container.status)

    def test_accounts_nodes_and_volume_options_are_isolated(self) -> None:
        """账号与宿主路径生成独立卷，未知卷配置失败关闭。:return: None。"""
        first = prepare_scratchpad_mount(self.runtime, self.row)
        other = {**self.row, 'environment_id': 'b' * 32}
        self.runtime._root(other).mkdir(parents=True, mode=0o700)
        second = prepare_scratchpad_mount(self.runtime, other)
        self.assertNotEqual(first['Source'], second['Source'])
        self.volumes[first['Source']].attrs['Options']['o'] += ',ro'
        with self.assertRaisesRegex(ValueError, '卷配置'):
            prepare_scratchpad_mount(self.runtime, self.row)

    def test_volume_retirement_keeps_files_and_published_data_requires_supported_node(self) -> None:
        """卷元数据移除保留文件，已发布数据拒绝未知节点能力。:return: None。"""
        mount = prepare_scratchpad_mount(self.runtime, self.row)
        marker = self.root / SCRATCHPAD_STORE / 'data/marker'
        marker.write_text('保留账号文件')
        remove_scratchpad_volume(self.runtime, self.row)
        self.assertEqual('保留账号文件', marker.read_text())
        self.assertNotIn(mount['Source'], self.volumes)
        prepare_scratchpad_mount(self.runtime, self.row)
        self.supported.return_value = False
        with self.assertRaisesRegex(ValueError, '兼容节点'):
            prepare_scratchpad_mount(self.runtime, self.row)
        self.assertEqual('保留账号文件', marker.read_text())



    def test_full_and_essential_backups_keep_scratchpad_data(self) -> None:
        """正式本机备份保全三会话的内容、权限与链接。:return: None。"""
        preserve_cli_scratchpad(self.runtime, self.row, self.container)
        prepare_scratchpad_mount(self.runtime, self.row)
        before = tree_inventory(self.root / SCRATCHPAD_STORE / 'data')
        for mode in ('full', 'essential'):
            target = self.parent / ('backup-' + mode)
            target.mkdir(mode=0o700)
            create_backup_data(self.data, target, excluded={}, mode=mode)
            verify_backup_data(target)
            self.assertEqual(before, tree_inventory(target / 'data/environments' / self.row['environment_id'] / SCRATCHPAD_STORE / 'data'))

    def test_unknown_runtime_directory_survives_backup_and_refuses_takeover(self) -> None:
        """历史同名文件保留在本机备份，挂载准备保持未知现场。:return: None。"""
        transient = self.root / SCRATCHPAD_RUNTIME
        transient.mkdir(mode=0o700)
        marker = transient / 'important.json'
        marker.write_text('historical-content')
        self.assertFalse(scratchpad_runtime_registered(self.root, self.row['environment_id']))
        target = self.parent / 'historical-backup'
        target.mkdir(mode=0o700)
        create_backup_data(self.data, target, excluded={}, mode='full')
        verify_backup_data(target)
        self.assertEqual('historical-content', (target / 'data/environments' / self.row['environment_id'] / SCRATCHPAD_RUNTIME / 'important.json').read_text())
        with self.assertRaisesRegex(ValueError, '未登记资料'):
            prepare_scratchpad_mount(self.runtime, self.row)
        self.assertEqual('historical-content', marker.read_text())
        self.client.volumes.create.assert_not_called()

    def test_registered_runtime_rejects_unknown_files_and_foreign_protocol(self) -> None:
        """已登记工作目录拒绝额外文件与外来环境回执，迁移排除失败关闭。:return: None。"""
        prepare_scratchpad_mount(self.runtime, self.row)
        transient = self.root / SCRATCHPAD_RUNTIME
        marker = transient / 'important.json'
        marker.write_text('preserved-content')
        with self.assertRaisesRegex(ValueError, '未知资料'):
            scratchpad_runtime_registered(self.root, self.row['environment_id'])
        self.assertEqual('preserved-content', marker.read_text())
        marker.unlink()
        atomic_json(transient / 'mount.json', {'protocol': 1, 'environment_id': 'b' * 32})
        with self.assertRaisesRegex(ValueError, '归属或协议'):
            prepare_scratchpad_mount(self.runtime, self.row)

    def test_corrupt_archive_and_foreign_identity_block_restore(self) -> None:
        """损坏内容及外来实例均阻挡恢复。:return: None。"""
        preserve_cli_scratchpad(self.runtime, self.row, self.container)
        self.container.id = 'other-cli'
        with self.assertRaisesRegex(ValueError, '原实例'):
            restore_cli_scratchpad(self.runtime, self.row, self.container)
        self.container.id = 'old-cli'
        self.container.attrs['State']['StartedAt'] = 'boot-two'
        receipt = json.loads((self.root / SCRATCHPAD_STORE / 'legacy.json').read_text())
        (self.root / SCRATCHPAD_STORE / receipt['archive']).write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, '摘要'):
            restore_cli_scratchpad(self.runtime, self.row, self.container)


if __name__ == '__main__':
    unittest.main()
