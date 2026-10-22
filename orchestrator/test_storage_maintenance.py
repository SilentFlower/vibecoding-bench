"""用真实文件、链接和权限验证冻结制品复用及写入隔离。"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import storage_maintenance
import storage_cleanup
from storage_maintenance import deduplicate_immutable_tree, tree_inventory
from storage_maintenance import acquire_storage_lock, read_storage_json
from storage_cleanup import apply_storage_plan, storage_plan


class ImmutableStorageTests(unittest.TestCase):
    """只读制品允许复用，可写路径、错误归属和变化中的文件保持隔离。"""

    def setUp(self) -> None:
        """准备受保护的临时树。@return None。"""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_real_dedup_preserves_logical_tree_and_is_idempotent(self) -> None:
        """盘点不写入，实际复用减少 inode，重复执行不再改动。@return None。"""
        for name in ('first', 'second', 'third'):
            (self.root / name).write_bytes('程序制品'.encode() * 1024)
        before = tree_inventory(self.root)
        result = deduplicate_immutable_tree(self.root, apply=False)
        self.assertEqual(2, result['relinked_files'])
        self.assertNotEqual((self.root / 'first').stat().st_ino, (self.root / 'second').stat().st_ino)
        result = deduplicate_immutable_tree(self.root)
        self.assertEqual(2, result['relinked_files'])
        self.assertEqual(before, tree_inventory(self.root))
        self.assertEqual(1, len({path.stat().st_ino for path in self.root.iterdir()}))
        self.assertEqual(0, deduplicate_immutable_tree(self.root)['relinked_files'])

    def test_writable_parent_and_different_modes_do_not_share(self) -> None:
        """组可写目录与执行权限不同的文件不能复用同一 inode。@return None。"""
        first, second = self.root / 'first', self.root / 'second'
        first.write_bytes(b'x' * 8192)
        second.write_bytes(first.read_bytes())
        second.chmod(0o755)
        directory = self.root / 'writable'
        directory.mkdir(mode=0o777)
        directory.chmod(0o777)
        third = directory / 'third'
        third.write_bytes(first.read_bytes())
        self.assertEqual(0, deduplicate_immutable_tree(self.root)['relinked_files'])
        self.assertNotEqual(first.stat().st_ino, second.stat().st_ino)
        self.assertNotEqual(first.stat().st_ino, third.stat().st_ino)

    def test_symlinks_never_modify_outside_files(self) -> None:
        """目录与文件链接均不穿越，根目录链接直接拒绝。@return None。"""
        outside = self.root / 'outside'
        outside.mkdir()
        protected = outside / 'protected'
        protected.write_bytes(b'x' * 8192)
        content = self.root / 'content'
        content.mkdir()
        (content / 'directory-link').symlink_to(outside, target_is_directory=True)
        (content / 'file-link').symlink_to(protected)
        (content / 'copy').write_bytes(protected.read_bytes())
        inode = protected.stat().st_ino
        self.assertEqual(0, deduplicate_immutable_tree(content)['relinked_files'])
        self.assertEqual(inode, protected.stat().st_ino)
        with self.assertRaises(OSError):
            deduplicate_immutable_tree(content / 'directory-link')

    def test_modified_target_between_inventory_and_replace_is_rejected(self) -> None:
        """实际盘点后变更目标应失败，不能用旧清单覆盖新字节。@return None。"""
        (self.root / 'first').write_bytes(b'x' * 8192)
        target = self.root / 'second'
        target.write_bytes(b'x' * 8192)
        original = storage_maintenance._parent
        changed = False

        def mutate(descriptor, relative):
            """仅在复用阶段开始时模拟并发写入。"""
            nonlocal changed
            if not changed:
                changed = True
                target.write_bytes(b'y' * 8192)
            return original(descriptor, relative)

        with patch.object(storage_maintenance, '_parent', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, '过期'):
                deduplicate_immutable_tree(self.root)
        self.assertEqual(b'y' * 8192, target.read_bytes())
        self.assertEqual(b'x' * 8192, (self.root / 'first').read_bytes())
        self.assertFalse(list(self.root.glob('.dedup-*')))

    def test_private_canonical_cache_shares_static_programs_only(self) -> None:
        """账号路径独立，但相同只读程序可复用管理端私有缓存。@return None。"""
        store = self.root / 'store'
        roots = []
        for name in ('account-a', 'account-b'):
            root = self.root / name
            root.mkdir(mode=0o755)
            (root / 'program').write_bytes(b'x' * 8192)
            roots.append(root)
            deduplicate_immutable_tree(root, canonical_root=store)
        self.assertEqual((roots[0] / 'program').stat().st_ino, (roots[1] / 'program').stat().st_ino)
        replacement = roots[0] / 'new-program'
        replacement.write_bytes(b'y' * 8192)
        replacement.replace(roots[0] / 'program')
        self.assertEqual(b'x' * 8192, (roots[1] / 'program').read_bytes())
        self.assertEqual(0o700, store.stat().st_mode & 0o777)

    @unittest.skipUnless(os.geteuid() == 0, '需要 root 切换到账号 UID1000 验证写入边界')
    def test_account_uid_cannot_modify_shared_program(self) -> None:
        """真实 UID1000 可读程序，但写入应被宿主权限拒绝。@return None。"""
        self.root.chmod(0o755)
        root = self.root / 'version'
        root.mkdir(mode=0o755)
        program = root / 'program'
        program.write_bytes(b'x' * 8192)
        program.chmod(0o644)
        deduplicate_immutable_tree(root, canonical_root=self.root / 'store')
        result = subprocess.run([str(Path(sys.executable).resolve()), '-c',
            'from pathlib import Path; import sys; Path(sys.argv[1]).write_bytes(b"modified")', str(program)],
            user=1000, group=1000, cwd='/tmp', capture_output=True)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(b'x' * 8192, program.read_bytes())

    def test_corrupt_canonical_cache_does_not_replace_private_program(self) -> None:
        """缓存散列不匹配时保留刚安装的私有程序。@return None。"""
        store = self.root / 'store'
        first = self.root / 'first'
        first.mkdir()
        (first / 'program').write_bytes(b'x' * 8192)
        deduplicate_immutable_tree(first, canonical_root=store)
        next(store.iterdir()).write_bytes(b'y' * 8192)
        second = self.root / 'second'
        second.mkdir()
        program = second / 'program'
        program.write_bytes(b'x' * 8192)
        with self.assertRaisesRegex(ValueError, '缓存'):
            deduplicate_immutable_tree(second, canonical_root=store)
        self.assertEqual(b'x' * 8192, program.read_bytes())

    def test_storage_operations_are_mutually_exclusive_and_release_on_close(self) -> None:
        """备份与启动不能同时认领同一部署，关闭句柄后可重试。@return None。"""
        descriptor = acquire_storage_lock(self.root)
        try:
            with self.assertRaisesRegex(ValueError, '已有'):
                acquire_storage_lock(self.root)
        finally:
            os.close(descriptor)
        os.close(acquire_storage_lock(self.root))

    def test_metadata_reader_refuses_pipe_and_link_without_waiting(self) -> None:
        """错误清单不能让停机维护等待 FIFO，也不能跟随链接读其他文件。@return None。"""
        document = self.root / 'plan.json'
        document.write_text('{"schema":1}')
        document.chmod(0o600)
        self.assertEqual({'schema': 1}, read_storage_json(document))
        alias = self.root / 'alias'
        alias.symlink_to(document)
        with self.assertRaises(OSError):
            read_storage_json(alias)
        pipe = self.root / 'pipe'
        os.mkfifo(pipe, 0o600)
        with self.assertRaisesRegex(ValueError, '类型'):
            read_storage_json(pipe)


class StorageCleanupTests(unittest.TestCase):
    """精确清理清单只触及下载缓存与冻结制品。"""

    def setUp(self) -> None:
        """准备合成账号、下载缓存、身份与冻结内容。@return None。"""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        environment = self.root / 'bench/environments' / ('a' * 32)
        self.cache = environment / 'home/.npm/_cacache'
        self.cache.mkdir(parents=True)
        (self.cache / 'download').write_bytes(b'cache' * 2048)
        self.identity = environment / 'home/.credentials.json'
        self.identity.write_text('synthetic-identity-preserved')
        self.frozen = self.root / 'bench/project-library/releases' / ('b' * 64)
        self.frozen.mkdir(parents=True)
        for name in ('first', 'second'):
            (self.frozen / name).write_bytes(b'x' * 8192)

    def test_clear_downloads_and_dedup_keep_identity_and_all_logical_files(self) -> None:
        """实际清理释放缓存，冻结目录全部逻辑内容与凭据保持原样。@return None。"""
        before = tree_inventory(self.frozen)
        result = apply_storage_plan(self.root, 'test', storage_plan(self.root, 'test'))
        self.assertEqual('passed', result['status'])
        self.assertFalse(self.cache.exists())
        self.assertEqual('synthetic-identity-preserved', self.identity.read_text())
        self.assertEqual(before, tree_inventory(self.frozen))
        self.assertEqual((self.frozen / 'first').stat().st_ino, (self.frozen / 'second').stat().st_ino)
        repeated = apply_storage_plan(self.root, 'test', storage_plan(self.root, 'test'))
        self.assertEqual([], repeated['removed_caches'])

    def test_invalid_later_path_refuses_before_deleting_first_cache(self) -> None:
        """整份清单须先校验，不能先删合法项再发现后续越界。@return None。"""
        plan = storage_plan(self.root, 'test')
        plan['content'].append({'path': str(self.identity.parent.relative_to(self.root)), 'inventory_sha256': '0' * 64})
        plan['plan_sha256'] = storage_cleanup._digest({key: value for key, value in plan.items() if key != 'plan_sha256'})
        with self.assertRaisesRegex(ValueError, '范围'):
            apply_storage_plan(self.root, 'test', plan)
        self.assertTrue(self.cache.exists())
        self.assertTrue(self.identity.exists())

    def test_cache_change_invalidates_plan_without_deletion(self) -> None:
        """盘点后出现新下载时必须重新盘点，旧清单不能删除新内容。@return None。"""
        plan = storage_plan(self.root, 'test')
        (self.cache / 'new-download').write_bytes(b'new')
        with self.assertRaisesRegex(ValueError, '变化'):
            apply_storage_plan(self.root, 'test', plan)
        self.assertTrue((self.cache / 'new-download').exists())

    def test_cache_parent_symlink_is_never_traversed(self) -> None:
        """用户父目录链接不能把维护动作带到部署外。@return None。"""
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / '_cacache').mkdir()
        protected = outside / '_cacache/protected'
        protected.write_bytes(b'preserved')
        original = self.cache.parent
        original.rename(original.with_name('old-npm'))
        original.symlink_to(outside, target_is_directory=True)
        plan = storage_plan(self.root, 'test')
        self.assertEqual([], plan['caches'])
        apply_storage_plan(self.root, 'test', plan)
        self.assertEqual(b'preserved', protected.read_bytes())


if __name__ == '__main__':
    unittest.main()
