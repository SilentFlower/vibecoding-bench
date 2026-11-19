"""验证远程节点数据根的独占归属、符号链接与清理续接。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from unittest.mock import patch

from cluster_removal_files import removal_files, verify_removal_mounts


class NodeRemovalFilesTests(unittest.TestCase):
    """在临时目录验证节点文件侧的归属和边界。"""

    def setUp(self) -> None:
        """生成独立数据根和原安装标记。:return: 无。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.parent = Path(temporary.name)
        self.root = self.parent / 'node'
        self.root.mkdir()
        self.owner = {'protocol': 1, 'deployment_id': 'test', 'node_key': 'a' * 32}
        marker = self.root / 'cluster-node.json'
        marker.write_text(json.dumps(self.owner))
        marker.chmod(0o600)

    def test_only_original_node_data_are_erased_and_repeat_is_idempotent(self) -> None:
        """符号链接和硬链接指向的其他节点资料保持完整。:return: 无。"""
        neighbor = self.parent / 'neighbor'
        neighbor.mkdir()
        survivor = neighbor / 'other-node-data'
        survivor.write_text('另一个节点的资料')
        (self.root / 'nested').mkdir()
        (self.root / 'nested' / 'log').write_text('原节点日志')
        (self.root / 'link').symlink_to(neighbor)
        (self.root / 'hard-link').hardlink_to(survivor)
        original = removal_files('probe', str(self.root), self.owner, None)
        self.assertEqual('owned', original['state'])
        expected = {'state': 'empty', 'identity': original['identity']}
        self.assertEqual(expected, removal_files('erase', str(self.root), self.owner, original['identity']))
        self.assertEqual(expected, removal_files('erase', str(self.root), self.owner, original['identity']))
        self.assertFalse(list(self.root.iterdir()))
        self.assertEqual('另一个节点的资料', survivor.read_text())

    def test_unowned_replaced_and_linked_directories_are_rejected(self) -> None:
        """标记不符、同路径换址及符号链接均在擦除前退出。:return: 无。"""
        original = removal_files('probe', str(self.root), self.owner, None)
        with self.assertRaisesRegex(ValueError, '身份不一致'):
            removal_files('erase', str(self.root), {**self.owner, 'node_key': 'b' * 32}, original['identity'])
        moved = self.root.rename(self.parent / 'original')
        self.root.mkdir()
        with self.assertRaisesRegex(ValueError, '已经换址'):
            removal_files('erase', str(self.root), self.owner, original['identity'])
        self.root.rmdir()
        self.root.symlink_to(moved)
        with self.assertRaises(OSError):
            removal_files('erase', str(self.root), self.owner, original['identity'])
        self.assertTrue((moved / 'cluster-node.json').is_file())

    def test_foreign_bind_sources_resolve_symlinks_and_keep_other_directories_available(self) -> None:
        """其他容器的目录别名按实际源判定，独立绑定可以共用宿主。:return: 无。"""
        sibling = self.parent / 'other-node'
        sibling.mkdir()
        child = self.root / 'logs'
        child.mkdir()
        paths = (self.root, self.parent, child)
        for index, target in enumerate(paths):
            alias = self.parent / f'alias-{index}'
            alias.symlink_to(target)
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, '其他容器仍在使用'):
                verify_removal_mounts(str(self.root), [str(alias)])
        alias = self.parent / 'other-node-alias'
        alias.symlink_to(sibling)
        self.assertEqual({'ok': True}, verify_removal_mounts(str(self.root), [str(alias)]))
        self.assertTrue((self.root / 'cluster-node.json').is_file())

    def test_own_mount_root_is_allowed_but_nested_mount_refuses_clear(self) -> None:
        """允许独立数据盘的根，子挂载须在任何数据清理前挡住。:return: 无。"""
        target = PurePosixPath(self.root)
        mount = ('42:0', PurePosixPath('/'), target)
        with patch('cluster_removal_files._mounts', return_value={'10': mount}):
            proof = removal_files('probe', str(self.root), self.owner, None)
        (self.root / 'nested').mkdir()
        (self.root / 'test-data').write_text('保留数据')
        with patch('cluster_removal_files._mounts', return_value={'10': mount,
                '11': ('42:1', PurePosixPath('/'), target / 'nested')}):
            with self.assertRaisesRegex(ValueError, '存在其他挂载'):
                removal_files('erase', str(self.root), self.owner, proof['identity'])
        self.assertTrue((self.root / 'test-data').is_file())
        with patch('cluster_removal_files._mounts', return_value={'10': mount}):
            self.assertEqual('empty', removal_files('erase', str(self.root), self.owner, proof['identity'])['state'])
        self.assertTrue(self.root.is_dir())
