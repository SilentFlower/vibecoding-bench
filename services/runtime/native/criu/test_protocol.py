"""恢复控制面严格输入和私有目录复制的边界回归。"""
import asyncio
import os
from pathlib import Path
import socket
import tempfile
import unittest

from protocol import command, freeze_tree, receive, send


class ProtocolBoundaryTest(unittest.TestCase):
    """拒绝跨越固定控制合同的命令。"""

    def test_rejects_paths_pids_commands_and_unknown_fields(self):
        """恢复只接受已登记标识与新挑战。@return 无。"""
        valid = {'type': 'restore', 'key': 'a' * 64, 'template': '11111111-1111-4111-8111-111111111111',
                 'worker': '22222222-2222-4222-8222-222222222222', 'nonce': 'b' * 64}
        self.assertEqual(command(valid), valid)
        for invalid in ({**valid, 'pid': 42}, {**valid, 'path': '/etc/shadow'}, {**valid, 'command': 'sh'},
                        {**valid, 'key': '../x'}, {**valid, 'nonce': 'b' * 63},
                        {**valid, 'worker': 'AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA'}, {**valid, 'type': 'exec'}, [], None):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                command(invalid)
        seed = {key: value for key, value in valid.items() if key != 'nonce'}
        seed.update(type='template', pid=True)
        with self.assertRaises(ValueError):
            command(seed)

    def test_freeze_rejects_links_special_files_foreign_owner_and_growth(self):
        """快照文件复制不会跟随种子可写链接。@return 无。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source'
            source.mkdir()
            (source / 'link').symlink_to('/etc/passwd')
            with self.assertRaises(OSError):
                freeze_tree(source, root / 'symlink-copy', os.getuid())
            (source / 'link').unlink()
            os.mkfifo(source / 'fifo')
            with self.assertRaisesRegex(ValueError, 'DIRECTORY_TYPE'):
                freeze_tree(source, root / 'fifo-copy', os.getuid())
            (source / 'fifo').unlink()
            with self.assertRaisesRegex(ValueError, 'DIRECTORY_OWNER'):
                freeze_tree(source, root / 'foreign-copy', os.getuid() + 1)
            with (source / 'large').open('wb') as file:
                file.truncate(16 * 1024 * 1024 + 1)
            with self.assertRaisesRegex(ValueError, 'DIRECTORY_LIMIT'):
                freeze_tree(source, root / 'large-copy', os.getuid())

    def test_frozen_copy_owns_independent_private_files(self):
        """冻结副本与源文件具有独立inode及私有权限。@return 无。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source'
            source.mkdir()
            (source / 'config').write_bytes(b'synthetic-account-state')
            freeze_tree(source, root / 'copy', os.getuid())
            copy = root / 'copy/config'
            self.assertEqual(copy.read_bytes(), b'synthetic-account-state')
            self.assertNotEqual(copy.stat().st_ino, (source / 'config').stat().st_ino)
            self.assertEqual(copy.stat().st_mode & 0o777, 0o600)
            (source / 'config').write_bytes(b'changed')
            self.assertEqual(copy.read_bytes(), b'synthetic-account-state')


class HandoffTest(unittest.IsolatedAsyncioTestCase):
    """核对控制帧边界与实际SCM_RIGHTS交接。"""

    async def test_receives_one_frame_without_consuming_next_phase(self):
        """同一批输入内的下一阶段ACK保留。@return 无。"""
        left, right = socket.socketpair()
        left.setblocking(False)
        right.setblocking(False)
        try:
            await asyncio.get_running_loop().sock_sendall(left, b'{"type":"start"}\n{"next":true}\n')
            self.assertEqual(await receive(right), {'type': 'start'})
            self.assertEqual(await receive(right), {'next': True})
        finally:
            left.close()
            right.close()

    async def test_rejects_oversized_control_before_json_parse(self):
        """超长控制请求有界退出。@return 无。"""
        left, right = socket.socketpair()
        left.setblocking(False)
        right.setblocking(False)
        try:
            await asyncio.get_running_loop().sock_sendall(left, b'x' * 4096)
            with self.assertRaisesRegex(ValueError, 'COMMAND_LIMIT'):
                await receive(right)
        finally:
            left.close()
            right.close()


if __name__ == '__main__':
    unittest.main()
