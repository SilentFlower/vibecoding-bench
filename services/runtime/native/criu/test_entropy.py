"""核对恢复随机源复位的进程归属与内存写入边界。"""
import hashlib
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import entropy


class EntropyBoundaryTest(unittest.TestCase):
    """以受控 procfs 夹具验证拒绝分支与唯一四字节写入。"""

    def setUp(self):
        """建立单个受限暂停进程夹具。@return 无。"""
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.pid = 4242
        self.process = self.root / str(self.pid)
        self.process.mkdir()
        self.status = ('PPid:\t1\nUid:\t1001\t1001\t1001\t1001\nCapEff:\t0000000000000000\n'
                       'NoNewPrivs:\t1\nSeccomp:\t2\n')
        (self.process / 'status').write_text(self.status)
        (self.process / 'stat').write_text('4242 (fixture) T ' + ' '.join(['0'] * 18 + ['12345']))
        self.thread = self.process / 'task' / str(self.pid)
        self.thread.mkdir(parents=True)
        (self.thread / 'status').write_text('State:\tT (stopped)\nTgid:\t4242\n')
        (self.process / 'smaps').write_text('00001000-00002000 rw-p 00000000 00:00 0\nVmFlags: rd wr mr mw me ac wf\n')
        self.memory = self.process / 'mem'
        self.original = bytes(4096) + b'\x01\x00\x00\x00' + bytes(4092)
        self.memory.write_bytes(self.original)
        (self.process / 'exe').write_bytes(b'trusted-image')
        self.proof = entropy.ProcessProof(self.pid, 1, '12345', hashlib.sha256(b'trusted-image').hexdigest())
        self.reader, self.writer = os.pipe()
        self.proc_patch = patch.object(entropy, 'PROC_ROOT', self.root)
        self.pid_patch = patch.object(entropy.os, 'pidfd_open', side_effect=lambda _pid: os.dup(self.reader))
        self.proc_patch.start()
        self.pid_patch.start()

    def tearDown(self):
        """释放夹具与真实管道。@return 无。"""
        self.pid_patch.stop()
        self.proc_patch.stop()
        os.close(self.reader)
        os.close(self.writer)
        self.temporary.cleanup()

    def test_writes_only_verified_flag_word(self):
        """成功仅清零唯一标志的四字节。@return 无。"""
        receipt = entropy.reset_fork_guard(self.proof)
        self.assertEqual(receipt, {'profile': entropy.PROFILE, 'guard_bytes': 4, 'stopped_threads': 1})
        self.assertEqual(self.memory.read_bytes(), bytes(8192))

    def test_refuses_foreign_generation_and_image(self):
        """错误父进程、启动代次和执行体均保持内存原文。@return 无。"""
        for proof in [replace(self.proof, owner=2), replace(self.proof, started='12346'),
                      replace(self.proof, image_sha256='a' * 64)]:
            with self.subTest(proof=proof), self.assertRaises(entropy.EntropyError):
                entropy.reset_fork_guard(proof)
            self.assertEqual(self.memory.read_bytes(), self.original)

    def test_refuses_unsafe_credentials_and_running_threads(self):
        """异常权限和运行线程均在写入前拒绝。@return 无。"""
        for status in [self.status.replace('1001', '0'), self.status.replace('CapEff:\t0000000000000000', 'CapEff:\t0000000000000001'),
                       self.status.replace('NoNewPrivs:\t1', 'NoNewPrivs:\t0'), self.status.replace('Seccomp:\t2', 'Seccomp:\t0')]:
            (self.process / 'status').write_text(status)
            with self.assertRaises(entropy.EntropyError):
                entropy.reset_fork_guard(self.proof)
            self.assertEqual(self.memory.read_bytes(), self.original)
        (self.process / 'status').write_text(self.status)
        (self.thread / 'status').write_text('State:\tS (sleeping)\nTgid:\t4242\n')
        with self.assertRaisesRegex(entropy.EntropyError, 'THREAD_STATE'):
            entropy.reset_fork_guard(self.proof)
        self.assertEqual(self.memory.read_bytes(), self.original)

    def test_refuses_ambiguous_pages_and_changed_contents(self):
        """多个候选页或变化内容均保持全部内存。@return 无。"""
        smaps = self.process / 'smaps'
        original = smaps.read_text()
        smaps.write_text(original + '00003000-00004000 rw-p 00000000 00:00 0\nVmFlags: rd wr wf\n')
        with self.assertRaisesRegex(entropy.EntropyError, 'ENTROPY_PROFILE'):
            entropy.reset_fork_guard(self.proof)
        self.assertEqual(self.memory.read_bytes(), self.original)
        smaps.write_text(original)
        changed = self.original[:4096] + bytes(4) + b'changed' + bytes(4085)
        self.memory.write_bytes(changed)
        with self.assertRaisesRegex(entropy.EntropyError, 'ENTROPY_PROFILE'):
            entropy.reset_fork_guard(self.proof)
        self.assertEqual(self.memory.read_bytes(), changed)

    def test_refuses_exited_process(self):
        """已退出的 pidfd 在元数据操作前拒绝。@return 无。"""
        os.close(self.writer)
        self.writer = os.open('/dev/null', os.O_RDONLY)
        with self.assertRaisesRegex(entropy.EntropyError, 'PROCESS_EXITED'):
            entropy.reset_fork_guard(self.proof)
        self.assertEqual(self.memory.read_bytes(), self.original)


if __name__ == '__main__':
    unittest.main()
