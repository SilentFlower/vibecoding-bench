"""恢复故障证据的隐私、首错关联和有界文件所有权回归。"""
import asyncio
from contextlib import redirect_stdout
import errno
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from diagnostics import FailureDiagnostic, RECORD_COUNT, RECORD_LIMIT, SIDECAR


class FailureDiagnosticTest(unittest.TestCase):
    """取证只能产生受控摘要，文件边界不能因错误输入放宽。"""

    def setUp(self) -> None:
        """准备独立私有根和实例。@return 无。"""
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.instance = self.root / 'instances' / str(uuid4())
        self.instance.mkdir(mode=0o700, parents=True)
        self.diagnostic = FailureDiagnostic(self.root, 'restore', str(uuid4()), str(uuid4()),
            instance=self.instance, stage='report_decode')

    def tearDown(self) -> None:
        """释放本测试持有的目录。@return 无。"""
        self.temporary.cleanup()

    def report(self, error: BaseException, diagnostic: FailureDiagnostic | None = None) -> dict:
        """捕获真实摘要输出。@param error 合成异常。@param diagnostic 可选上下文。@return JSON事件。"""
        output = io.StringIO()
        with redirect_stdout(output):
            (diagnostic or self.diagnostic).report(error)
        return json.loads(output.getvalue())

    def test_errno_and_unknown_exception_never_copy_messages_or_paths(self) -> None:
        """精确保留errno，未知类型与异常原文均不可泄漏。@return 无。"""
        secret = 'Bearer synthetic-secret user@example.invalid /private/account/session\n原始业务正文'
        event = self.report(PermissionError(errno.EACCES, secret, secret))
        self.assertEqual(event['diagnostic']['errno'], errno.EACCES)
        self.assertEqual(event['diagnostic']['exception_type'], 'PermissionError')
        self.assertEqual(event['diagnostic']['stage'], 'report_decode')
        self.assertEqual(event['diagnostic']['upstream_status'], 'missing')
        custom = type('BearerSyntheticSecret', (Exception,), {})
        event = self.report(custom(secret))
        self.assertEqual(event['diagnostic']['exception_type'], 'UnknownError')
        for path in (self.root / 'failures').iterdir():
            raw = path.read_text()
            for forbidden in ('Bearer', 'synthetic-secret', 'example.invalid', '/private', '原始业务正文'):
                self.assertNotIn(forbidden, raw)
        self.assertNotIn(secret, json.dumps(event))

    def test_controlled_reason_and_errno_bounds(self) -> None:
        """只接纳受控reason与整数errno。@return 无。"""
        event = self.report(ValueError('RESTORE_IMAGE_MAPPING'))
        self.assertEqual(event['diagnostic']['reason'], 'RESTORE_IMAGE_MAPPING')
        for code in (True, 0, -1, 4096):
            error = OSError()
            error.errno = code
            self.assertIsNone(self.report(error)['diagnostic']['errno'])

    def test_process_failure_and_timeout_do_not_copy_command_or_output(self) -> None:
        """子进程命令、输出和超时文本均留在白名单摘要之外。@return 无。"""
        secret = 'Bearer process-secret /private/account user@example.invalid'
        error = subprocess.CalledProcessError(27, [secret], output=secret, stderr=secret)
        event = self.report(error)
        self.assertEqual(event['diagnostic']['process_returncode'], 27)
        self.assertEqual(event['diagnostic']['exception_type'], 'CalledProcessError')
        self.assertNotIn('process-secret', json.dumps(event))
        timeout = subprocess.TimeoutExpired([secret], 30, output=secret, stderr=secret)
        event = self.report(timeout)
        self.assertEqual(event['diagnostic']['exception_type'], 'TimeoutExpired')
        self.assertIsNone(event['diagnostic']['process_returncode'])
        self.assertNotIn('process-secret', json.dumps(event))

    def test_criu_tail_records_source_and_category_without_raw_text(self) -> None:
        """有界尾部只提取源码位置与错误分类，警告保持独立。@return 无。"""
        path = self.instance / 'restore.log'
        path.write_text('PRIVATE_PREFIX' * 3000 + '\n'
            'Error (criu/memfd.c:123): Permission denied /private/bearer-secret\n'
            'Warn (criu/secret-account.c:456): No such file user@example.invalid\n')
        path.chmod(0o600)
        self.diagnostic.log = path
        event = self.report(ValueError('RESTORE_IMAGE_IDENTITY'))
        record = event['diagnostic']
        self.assertEqual(record['log_status'], 'available_tail')
        self.assertEqual(record['log_evidence'][0], {'level': 'error', 'category': 'permission_denied',
            'module': 'memfd.c', 'line': 123})
        self.assertEqual(record['log_evidence'][1], {'level': 'warning', 'category': 'file_missing',
            'module': None, 'line': None})
        self.assertLess(len(json.dumps(record)), RECORD_LIMIT)
        for secret in ('PRIVATE_PREFIX', '/private', 'bearer-secret', 'secret-account', 'example.invalid'):
            self.assertNotIn(secret, json.dumps(event))

    def test_only_eight_log_evidence_entries_are_retained(self) -> None:
        """大量受控日志条目保持固定上限。@return 无。"""
        path = self.instance / 'restore.log'
        path.write_text(''.join(f'Error (criu/memfd.c:{number}): File exists\n' for number in range(1, 100)))
        path.chmod(0o600)
        self.diagnostic.log = path
        self.assertEqual(len(self.report(RuntimeError())['diagnostic']['log_evidence']), 8)

    def test_actual_criu_empty_image_error_keeps_controlled_source_and_category(self) -> None:
        """真实CRIU4.2空映像错误仅保留分类与已核验源码位置。@return 无。"""
        path = self.instance / 'restore.log'
        path.write_text('Warn  (criu/crtools.c:269): Stopped and detached shell job will get SIGHUP from OS.\n'
                        'Error (criu/protobuf.c:72): Unexpected EOF on (empty-image)\n')
        path.chmod(0o600)
        self.diagnostic.log = path
        evidence = self.report(RuntimeError())['diagnostic']['log_evidence']
        self.assertEqual(evidence[0], {'level':'error', 'category':'unexpected_eof', 'module':'protobuf.c', 'line':72})
        self.assertEqual(evidence[1]['level'], 'warning')
        self.assertEqual(evidence[1]['module'], 'crtools.c')

    def test_rotation_and_permissions_are_bounded(self) -> None:
        """第33条按受控时间轮换，权限和单条大小保持私有。@return 无。"""
        first = None
        for index in range(RECORD_COUNT + 1):
            with patch('diagnostics.time.time', return_value=1000 + index):
                self.assertEqual(self.report(OSError(errno.EMFILE, 'secret'))['persistence'], 'saved')
            if index == 0:
                first = next((self.root / 'failures').iterdir())
        files = list((self.root / 'failures').iterdir())
        self.assertEqual(len(files), RECORD_COUNT)
        self.assertFalse(first.exists())
        self.assertEqual(stat.S_IMODE((self.root / 'failures').stat().st_mode), 0o700)
        for path in files:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(path.stat().st_nlink, 1)
            self.assertLessEqual(path.stat().st_size, RECORD_LIMIT)
        self.assertEqual(len(list(self.instance.iterdir())), 0)

    def test_upstream_survives_instance_cleanup_and_preserves_derived_error(self) -> None:
        """原监督失败和后续空报告分别保存，实例删除后首错仍可读。@return 无。"""
        child = FailureDiagnostic(self.root, 'restore', instance=self.instance,
            stage='criu_restore', criu_returncode=27)
        child.report(SystemExit(111), supervisor=True)
        with self.assertRaises(json.JSONDecodeError) as caught:
            json.loads(b'')
        event = self.report(caught.exception)
        shutil.rmtree(self.instance)
        record = json.loads(next((self.root / 'failures').iterdir()).read_text())
        self.assertEqual(record, event['diagnostic'])
        self.assertEqual(record['exception_type'], 'JSONDecodeError')
        self.assertEqual(record['stage'], 'report_decode')
        self.assertEqual(record['upstream_status'], 'available')
        self.assertEqual(record['upstream']['stage'], 'criu_restore')
        self.assertEqual(record['upstream']['criu_returncode'], 27)
        self.assertEqual(record['upstream']['process_returncode'], 111)
        self.assertEqual(record['upstream']['reason'], 'CRIU_EXIT_NONZERO')

    def test_sidecar_is_exclusive_and_original_evidence_is_preserved(self) -> None:
        """后续写入不得覆盖本实例首错。@return 无。"""
        child = FailureDiagnostic(self.root, 'restore', instance=self.instance, stage='pid_setup')
        child.report(FileNotFoundError(errno.ENOENT, 'secret'), supervisor=True)
        before = (self.instance / SIDECAR).read_bytes()
        with redirect_stdout(io.StringIO()):
            child.report(RuntimeError('replacement-secret'), supervisor=True)
        self.assertEqual((self.instance / SIDECAR).read_bytes(), before)
        self.assertEqual([p.name for p in self.instance.iterdir()], [SIDECAR])

    def test_bad_sidecars_are_explicitly_invalid_and_never_exposed(self) -> None:
        """额外字段、重复键、超限、嵌套与跨实例摘要都拒绝。@return 无。"""
        child = FailureDiagnostic(self.root, 'restore', instance=self.instance, stage='criu_restore')
        child.report(RuntimeError(), supervisor=True)
        valid = json.loads((self.instance / SIDECAR).read_text())
        wrong_instance = dict(valid, instance=str(uuid4()))
        nested = dict(valid, upstream_status='available', upstream=valid)
        invalid_values = [json.dumps(dict(valid, secret='Bearer secret')), json.dumps(wrong_instance),
            json.dumps(nested), '{"schema_version":1,"schema_version":2}', 'x' * (RECORD_LIMIT + 1),
            json.dumps(dict(valid, stage=['secret'])), json.dumps(dict(valid, schema_version=True))]
        for raw in invalid_values:
            with self.subTest(raw_length=len(raw)):
                (self.instance / SIDECAR).write_text(raw)
                event = self.report(ValueError('secret'))
                self.assertEqual(event['diagnostic']['upstream_status'], 'invalid')
                self.assertIsNone(event['diagnostic']['upstream'])
                self.assertNotIn('Bearer', json.dumps(event))

    def test_sidecar_links_fifo_and_loose_permissions_are_rejected(self) -> None:
        """副摘要只能是私有单链接普通文件，FIFO读取不阻塞。@return 无。"""
        outside = self.root / 'outside'
        outside.write_bytes(b'PRIVATE')
        outside.chmod(0o600)
        sidecar = self.instance / SIDECAR
        for kind in ('symlink', 'hardlink', 'fifo', 'loose'):
            with self.subTest(kind=kind):
                if kind == 'symlink':
                    sidecar.symlink_to(outside)
                elif kind == 'hardlink':
                    os.link(outside, sidecar)
                elif kind == 'fifo':
                    os.mkfifo(sidecar, 0o600)
                else:
                    sidecar.write_bytes(b'PRIVATE')
                    sidecar.chmod(0o644)
                event = self.report(OSError(errno.EIO, 'secret'))
                self.assertEqual(event['diagnostic']['upstream_status'], 'invalid')
                sidecar.unlink()
        self.assertEqual(outside.read_bytes(), b'PRIVATE')

    @unittest.skipUnless(os.geteuid() == 0, '外来属主验证需要root测试上下文')
    def test_foreign_owner_sidecar_is_rejected(self) -> None:
        """业务UID写入的文件不能充当可信监督摘要。@return 无。"""
        sidecar = self.instance / SIDECAR
        sidecar.write_bytes(b'PRIVATE')
        sidecar.chmod(0o600)
        os.chown(sidecar, 1001, 1001)
        self.assertEqual(self.report(RuntimeError())['diagnostic']['upstream_status'], 'invalid')

    def test_unsafe_store_preserves_foreign_files_and_still_emits_metadata(self) -> None:
        """外来文件与链接不参与轮换，安全摘要仍可从普通日志检索。@return 无。"""
        self.report(RuntimeError())
        directory = self.root / 'failures'
        foreign = directory / 'keep.txt'
        foreign.write_bytes(b'KEEP')
        event = self.report(OSError(errno.ENOSPC, 'secret'))
        self.assertEqual(event['persistence'], 'DIAGNOSTIC_STORE_FAILED')
        self.assertEqual(event['diagnostic']['errno'], errno.ENOSPC)
        self.assertEqual(foreign.read_bytes(), b'KEEP')
        foreign.unlink()
        existing = next(directory.iterdir())
        os.link(existing, directory / (str(uuid4()) + '.json'))
        before = {p.name:p.read_bytes() for p in directory.iterdir()}
        self.assertEqual(self.report(RuntimeError())['persistence'], 'DIAGNOSTIC_STORE_FAILED')
        self.assertEqual({p.name:p.read_bytes() for p in directory.iterdir()}, before)

    def test_store_and_parent_links_are_rejected(self) -> None:
        """逐级打开拒绝父链接和存储目录链接。@return 无。"""
        outside = self.root / 'outside'
        outside.mkdir(mode=0o700)
        (self.root / 'failures').symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.report(RuntimeError())['persistence'], 'DIAGNOSTIC_STORE_FAILED')
        self.assertEqual(list(outside.iterdir()), [])
        alias = self.root / 'alias'
        alias.symlink_to(outside, target_is_directory=True)
        (outside / 'child').mkdir(mode=0o700)
        diagnostic = FailureDiagnostic(alias / 'child', 'template', stage='template_dump')
        self.assertEqual(self.report(RuntimeError(), diagnostic)['persistence'], 'DIAGNOSTIC_STORE_FAILED')

    def test_partial_write_failure_removes_temporary_and_releases_descriptors(self) -> None:
        """真实临时文件部分写入后磁盘失败，原异常摘要仍可从日志读取。@return 无。"""
        original = os.write
        writes = []

        def write(descriptor, data):
            """先完成短写再注入磁盘满。@param descriptor 实际文件FD。@param data 待写摘要。@return 首次写入量。"""
            if writes:
                raise OSError(errno.ENOSPC, 'private-secret')
            writes.append(descriptor)
            return original(descriptor, data[:10])

        before = len(list(Path('/proc/self/fd').iterdir()))
        with patch('diagnostics.os.write', side_effect=write):
            event = self.report(OSError(errno.EMFILE, 'original-secret'))
        self.assertEqual(event['persistence'], 'DIAGNOSTIC_STORE_FAILED')
        self.assertEqual(event['diagnostic']['errno'], errno.EMFILE)
        self.assertEqual(list((self.root / 'failures').iterdir()), [])
        self.assertEqual(len(list(Path('/proc/self/fd').iterdir())), before)

    def test_unsafe_store_permissions_and_corrupt_records_are_preserved(self) -> None:
        """私有存储权限漂移和损坏旧摘要都显式失败，原文件保持。@return 无。"""
        self.report(RuntimeError())
        directory = self.root / 'failures'
        path = next(directory.iterdir())
        original = path.read_bytes()
        directory.chmod(0o755)
        self.assertEqual(self.report(RuntimeError())['persistence'], 'DIAGNOSTIC_STORE_FAILED')
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o755)
        directory.chmod(0o700)
        path.write_bytes(b'{"secret":"PRIVATE"}')
        self.assertEqual(self.report(RuntimeError())['persistence'], 'DIAGNOSTIC_STORE_FAILED')
        self.assertEqual(path.read_bytes(), b'{"secret":"PRIVATE"}')

    def test_cancellation_and_diagnostic_output_failure_preserve_control_flow(self) -> None:
        """正常取消不生成事故；诊断输出故障保持原异常归属。@return 无。"""
        with redirect_stdout(io.StringIO()) as output:
            self.diagnostic.report(asyncio.CancelledError())
            self.diagnostic.report(ValueError('RESTORE_CONNECTION_CLOSED'))
        self.assertEqual(output.getvalue(), '')
        self.assertFalse((self.root / 'failures').exists())
        with patch('diagnostics._store', side_effect=OSError(errno.ENOSPC, 'secret')), patch(
                'sys.stdout.write', side_effect=BrokenPipeError(errno.EPIPE, 'secret')):
            self.diagnostic.report(RuntimeError('original-secret'))


class SupervisorFailureProcessTest(unittest.TestCase):
    """监督子进程真实退出后，控制器能够保留上游首错。"""

    def test_nonzero_criu_exit_keeps_sidecar_before_report_eof(self) -> None:
        """真实FD与子进程复现空报告，模拟固定CRIU命令返回27。@return 无。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            instance = root / 'instances' / str(uuid4())
            instance.mkdir(mode=0o700, parents=True)
            configuration = {'work_root': str(root / 'native'), 'source_root': str(root / 'source'),
                'source_max_pid': 42, 'images': str(root / 'images'), 'pipes': {'0':'pipe:[1]', '1':'pipe:[2]', '2':'pipe:[3]'}}
            (instance / 'config.json').write_text(json.dumps(configuration))
            descriptors = []
            for _ in range(5):
                descriptors.extend(os.pipe())
            image = os.open('/dev/null', os.O_RDONLY)
            descriptors.append(image)
            gate_r, gate_w, report_r, report_w, incoming_r, incoming_w, outgoing_r, outgoing_w, errors_r, errors_w, _ = descriptors
            program = '''import json,sys,subprocess
from pathlib import Path
import supervisor
root=Path(sys.argv[1]); identifier=sys.argv[2]
supervisor.ROOT=root
original_path=Path
def private_path(*parts):
    """仅重定向内核PID计数文件。@param parts 路径片段。@return 合成文件路径。"""
    path=original_path(*parts)
    return root/'ns_last_pid' if str(path)=='/proc/sys/kernel/ns_last_pid' else path
def command(arguments,**kwargs):
    """隔离挂载及CRIU执行。@param arguments 原参数。@param kwargs 原选项。@return 固定子命令状态。"""
    return subprocess.CompletedProcess(arguments,27 if arguments[0]=='/opt/ccrb-criu/criu' else 0)
supervisor.Path=private_path
supervisor.os.getpid=lambda:1
supervisor.subprocess.run=command
sys.argv=['supervisor',identifier,*sys.argv[3:]]
supervisor.main()
'''
            inherited = (gate_r, report_w, incoming_r, outgoing_w, errors_w, image)
            try:
                os.write(gate_w, b'S')
                process = subprocess.run([sys.executable, '-c', program, str(root), instance.name,
                    *(str(fd) for fd in inherited)], pass_fds=inherited, capture_output=True, text=True,
                    env={**os.environ, 'PYTHONPATH': str(Path(__file__).parent)}, timeout=10)
                self.assertEqual(process.returncode, 111, process.stderr)
                os.close(report_w)
                descriptors.remove(report_w)
                self.assertEqual(os.read(report_r, 4096), b'')
                output = io.StringIO()
                with redirect_stdout(output):
                    FailureDiagnostic(root, 'restore', instance=instance, stage='report_decode').report(json.JSONDecodeError('private-secret', '', 0))
                record = json.loads(output.getvalue())['diagnostic']
                self.assertEqual(record['upstream_status'], 'available')
                self.assertEqual(record['upstream']['criu_returncode'], 27)
                self.assertEqual(record['upstream']['stage'], 'criu_restore')
                self.assertEqual(record['upstream']['source']['module'], 'supervisor.py')
                self.assertNotIn('private-secret', output.getvalue())
                shutil.rmtree(instance)
                self.assertEqual(len(list((root / 'failures').iterdir())), 1)
            finally:
                for descriptor in descriptors:
                    os.close(descriptor)


if __name__ == '__main__':
    unittest.main()
