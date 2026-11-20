"""核对 AGY 快照临时目录回收前记录的受控错误证据。"""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from agy import AgyController


class AgyCheckpointDiagnosticTest(unittest.IsolatedAsyncioTestCase):
    """AGY 快照诊断应保留阶段和退出码，并只记录允许输出的错误信息。"""

    async def test_dump_failure_reports_safe_evidence_before_cleanup(self):
        """用真实非零退出触发诊断并校验脱敏。@return 无。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / 'criu-fixture'
            executable.write_text(f'#!{sys.executable}\n' + '''
import os
import sys

log = sys.argv[sys.argv.index('--log-file') + 1]
with open(os.open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
    stream.write("Error (criu/fsnotify.c:284): synthetic-secret: Can't dump that handle\\n")
raise SystemExit(7)
''')
            executable.chmod(0o700)
            controller = AgyController(1, root, executable, root)
            stdout = io.StringIO()
            with redirect_stdout(stdout), self.assertRaisesRegex(ValueError, '^AGY_CRIU_DUMP$'):
                await controller.run('dump', root, ['--tree', '123'])
        self.assertEqual(json.loads(stdout.getvalue()), {
            'layer': 'agy_criu_controller', 'stage': 'dump', 'criu_returncode': 7,
            'log_status': 'available_tail',
            'log_evidence': [{'level': 'error', 'category': 'file_handle_unresolved', 'module': 'fsnotify.c', 'line': 284}],
        })

    def test_worker_scan_uses_only_the_supervisor_work_directory(self):
        """固定扫描范围，并拒绝同名链接和其他工作根。@return 无。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workers = root / 'workers'
            worker = workers / ('a' * 32)
            worker.mkdir(parents=True)
            outside = root / ('b' * 32)
            outside.mkdir()
            linked = workers / ('b' * 32)
            linked.symlink_to(outside, target_is_directory=True)
            controller = AgyController(1, root, root / 'criu', root)
            with patch.object(Path, 'read_bytes', return_value=f'TMPDIR={worker}\0'.encode()):
                self.assertEqual(controller._worker_directory(123), worker)
            for directory in (outside, linked):
                with self.subTest(directory=directory), \
                        patch.object(Path, 'read_bytes', return_value=f'TMPDIR={directory}\0'.encode()), \
                        self.assertRaisesRegex(ValueError, '^AGY_CRIU_DUMP$'):
                    controller._worker_directory(123)
