"""可信入口回退时仍须保持降权与业务过滤器完整。"""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import entry


class EntryBoundaryTest(unittest.TestCase):
    """核对目录遍历权限与不可绕过的降权入口准入。"""

    def test_private_umask_keeps_sender_socket_traversal(self):
        """umask077下仍允许固定业务组访问控制socket。@return 无。"""
        with tempfile.TemporaryDirectory() as temporary, patch('entry.os.chown') as chown:
            directory = Path(temporary) / 'control'
            previous = os.umask(0o077)
            try:
                entry.socket_directory(directory)
            finally:
                os.umask(previous)
            self.assertEqual(directory.stat().st_mode & 0o777, 0o750)
            chown.assert_called_once_with(directory, 0, 1001)

    def test_shared_restore_requires_matching_tool_capability(self):
        """旧工具画像走恢复预检拒绝，避免错用独立映像恢复。@return 无。"""
        profile = {'protocol': 1, 'entropy_profile': 'bun143-wipeonfork-v1',
            'criu': {'source_version': '4.2', 'memfd_executable_restore': 1}, 'files': {}}
        context = 'Seccomp:\t0\nCapEff:\tffffffffffffffff\n'
        with patch.object(entry.os, 'getuid', return_value=0), patch.object(Path, 'read_text', return_value=context):
            with self.assertRaisesRegex(ValueError, 'PROFILE_INVALID'):
                entry.preflight(profile)
            profile['criu']['shared_memfd_restore'] = 1
            self.assertEqual(entry.preflight(profile), profile)

    @unittest.skipUnless(os.getuid() == 0, '降权入口的实际root所有权检查需要root测试环境')
    def test_changed_filter_stops_before_any_fallback_exec(self):
        """恢复能力失败也不得借用已变化的业务过滤器。@return 无。"""
        with tempfile.TemporaryDirectory() as temporary:
            tools = Path(temporary)
            digests = {}
            for name in ('launch', 'business-seccomp.bpf'):
                path = tools / name
                path.write_bytes(b'synthetic-' + name.encode())
                path.chmod(0o644)
                digests[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            profile = {'files': digests}
            (tools / 'profile.json').write_text(json.dumps(profile))
            (tools / 'profile.json').chmod(0o644)
            with patch.object(entry, 'TOOLS', tools):
                self.assertEqual(entry.dispatcher(), profile)
                (tools / 'business-seccomp.bpf').write_bytes(b'changed-policy')
                with self.assertRaisesRegex(ValueError, 'DISPATCHER_IDENTITY'):
                    entry.dispatcher()


if __name__ == '__main__':
    unittest.main()
