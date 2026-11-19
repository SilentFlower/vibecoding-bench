"""使用真实文件、进程和回环 HTTP 验证 AGY 凭据离线参考合同。"""
import copy
import json
import os
import select
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs

from verify_agy_credentials import CredentialLab, TOKEN_PATH, access_document, native_document, native_probe, private_json, retry_allowed
from runtime_files import atomic_json


def _document():
    """建立仅用于离线实验的合成原生结构。"""
    return {'auth_method': 'consumer', 'id_token_email': 'fixture@example.test',
        'token': {'access_token': 'synthetic-at-1', 'refresh_token': 'synthetic-rt-1',
            'token_type': 'Bearer', 'expires_in': 3600,
            'expiry': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}}


class _RefreshHandler(BaseHTTPRequestHandler):
    """由测试屏障控制的本地 OAuth 轮换服务。"""

    def log_message(self, *args):
        """静默处理 HTTP 日志。

        :param args: 原 HTTP 日志参数。
        :return: 无。
        """

    def do_POST(self):
        """实际接收并轮换合成刷新令牌。

        :return: 无，响应写入回环连接。
        """
        fields = parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode())
        with self.server.guard:
            self.server.calls += 1
            number = self.server.calls
            valid = fields.get('refresh_token') == [self.server.expected]
            self.server.expected = 'synthetic-rt-' + str(number + 1)
        self.server.received.set()
        self.server.release.wait(3)
        if self.server.mode == 'disconnect':
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        result = {'access_token': 'synthetic-at-' + str(number + 1),
            'refresh_token': self.server.expected, 'expires_in': 3600}
        if self.server.mode == 'same-refresh':
            result.pop('refresh_token')
            self.server.expected = fields['refresh_token'][0]
        payload = b'{' if self.server.mode == 'malformed' else json.dumps(result).encode()
        self.send_response(200 if valid else 400)
        self.end_headers()
        try:
            self.wfile.write(payload)
        except BrokenPipeError:
            pass


_CACHE_WORKER = '''import json,sys
from pathlib import Path
cached=json.loads(Path(sys.argv[1]).read_text())['token']['access_token']
pending=None
print(json.dumps({'event':'ready'}),flush=True)
for line in sys.stdin:
 value=json.loads(line)
 if value['action']=='start':
  pending=(value['owner'],value['call'])
  print(json.dumps({'event':'chunk','owner':pending[0],'call':pending[1]}),flush=True)
 elif value['action']=='result':
  if pending != (value['owner'],value['call']):
   print(json.dumps({'event':'rejected'}),flush=True)
  else:
   with Path(sys.argv[2]).open('a') as output:output.write('effect\\n')
   pending=None
   print(json.dumps({'event':'complete','uses_original':cached==value['expected']}),flush=True)
 elif value['action']=='stop':
  print(json.dumps({'event':'stopped','pending':pending is not None}),flush=True)
  break
'''


_PROBE_WORKER = '''import json,sys
from pathlib import Path
import verify_agy_credentials as verifier
verifier.NATIVE_TEST_ROOT=Path(sys.argv[1])
def probe(config,root):
 def record(stage):
  with (root/'probe-effects').open('a') as output:output.write(config['run_id']+':'+stage+'\\n')
 record('preflight')
 print(json.dumps({'event':'ready'}),flush=True)
 if json.loads(input())['action']!='refresh':raise ValueError('实验阶段无效')
 record('refresh')
 print(json.dumps({'event':'refreshed'}),flush=True)
 if json.loads(input())['action']!='restore':raise ValueError('实验阶段无效')
 record('restore')
 return {'event':'complete'}
verifier._native_probe_locked=probe
try:result=verifier.native_probe({'run_id':sys.argv[2]})
except ValueError as error:result={'event':'rejected','reason':str(error)}
print(json.dumps(result),flush=True)
'''


class AgyCredentialTests(unittest.TestCase):
    """离线结果显式标记为参考模型，原生结果由独立实验记录。"""

    def setUp(self):
        """建立私有目录和可控回环服务。

        :return: 无。
        """
        self.temporary = tempfile.TemporaryDirectory(prefix='agy-credential-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.document = _document()
        self.lab = CredentialLab(self.root / 'manager', self.document)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), _RefreshHandler)
        self.server.daemon_threads = True
        self.server.guard = threading.Lock()
        self.server.calls = 0
        self.server.expected = 'synthetic-rt-1'
        self.server.mode = 'normal'
        self.server.received = threading.Event()
        self.server.release = threading.Event()
        self.server.release.set()
        self.thread = threading.Thread(target=self.server.serve_forever,
            kwargs={'poll_interval': 0.01}, daemon=True)
        self.thread.start()
        self.addCleanup(self._close_server)
        self.endpoint = 'http://127.0.0.1:' + str(self.server.server_port) + '/token'
        self.destination = self.root / 'worker' / TOKEN_PATH

    def _close_server(self):
        """释放屏障并关闭实验服务。"""
        self.server.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def _worker(self):
        """启动模拟常驻凭据缓存与工具归属的真实子进程。"""
        self.assertTrue(self.lab.publish(1, self.destination))
        process = subprocess.Popen([sys.executable, '-u', '-c', _CACHE_WORKER,
            str(self.destination), str(self.root / 'effects')], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'HOME': str(self.root)})
        self.addCleanup(self._close_worker, process)
        self.assertEqual(self._reply(process)['event'], 'ready')
        return process

    def _close_worker(self, process):
        """回收本测试创建的进程与管道。"""
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=3)

    def _reply(self, process):
        """有界读取子进程的一条真实输出。"""
        ready, _, _ = select.select([process.stdout], [], [], 3)
        self.assertTrue(ready, '实验子进程未按时响应')
        return json.loads(process.stdout.readline())

    def _send(self, process, value):
        """写入本测试的控制信封并读取回执。"""
        process.stdin.write(json.dumps(value) + '\n')
        process.stdin.flush()
        return self._reply(process)

    def _probe_worker(self, run_id):
        """通过真实子进程进入原生探针入口，仅替换锁内的外部实验。"""
        process = subprocess.Popen([sys.executable, '-u', '-c', _PROBE_WORKER,
            str(self.root), run_id], cwd=Path(__file__).parent, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self._close_worker, process)
        return process

    def test_native_probe_lock_covers_preflight_refresh_and_restore(self):
        """独立进程竞争时，恢复完成前只有原所有者可进入环境重检及刷新。

        :return: 无。
        """
        first = self._probe_worker('first')
        self.assertEqual(self._reply(first)['event'], 'ready')
        for stage in ('preflight', 'refresh'):
            contender = self._probe_worker('contender-' + stage)
            reply = self._reply(contender)
            self.assertEqual(reply['event'], 'rejected')
            self.assertIn('正在接管', reply['reason'])
            self.assertEqual(contender.wait(timeout=3), 0)
            if stage == 'preflight':
                self.assertEqual(self._send(first, {'action': 'refresh'})['event'], 'refreshed')
        self.assertEqual(self._send(first, {'action': 'restore'})['event'], 'complete')
        self.assertEqual(first.wait(timeout=3), 0)
        second = self._probe_worker('second')
        self.assertEqual(self._reply(second)['event'], 'ready')
        self.assertEqual(self._send(second, {'action': 'refresh'})['event'], 'refreshed')
        self.assertEqual(self._send(second, {'action': 'restore'})['event'], 'complete')
        self.assertEqual(second.wait(timeout=3), 0)
        self.assertEqual((self.root / 'probe-effects').read_text().splitlines(),
            ['first:preflight', 'first:refresh', 'first:restore',
             'second:preflight', 'second:refresh', 'second:restore'])
        self.assertEqual((self.root / 'credential-contract.lock').stat().st_mode & 0o777, 0o600)

    def test_native_probe_lock_releases_after_owner_process_death(self):
        """实际终止锁持有进程后，新探针可重新进入受保护的环境重检。

        :return: 无。
        """
        first = self._probe_worker('interrupted')
        self.assertEqual(self._reply(first)['event'], 'ready')
        first.kill()
        first.wait(timeout=3)
        second = self._probe_worker('recovery')
        self.assertEqual(self._reply(second)['event'], 'ready')
        self.assertEqual(self._send(second, {'action': 'refresh'})['event'], 'refreshed')
        self.assertEqual(self._send(second, {'action': 'restore'})['event'], 'complete')
        self.assertEqual(second.wait(timeout=3), 0)
        self.assertEqual((self.root / 'probe-effects').read_text().splitlines(),
            ['interrupted:preflight', 'recovery:preflight', 'recovery:refresh', 'recovery:restore'])

    def test_native_probe_rejects_shared_or_linked_lock_before_preflight(self):
        """锁权限扩大或被换成链接时，在环境访问前拒绝接管。

        :return: 无。
        """
        lock = self.root / 'credential-contract.lock'
        lock.touch(mode=0o644)
        with patch('verify_agy_credentials.NATIVE_TEST_ROOT', self.root), \
                patch('verify_agy_credentials._native_probe_locked') as probe:
            with self.assertRaisesRegex(ValueError, '权限无效'):
                native_probe({'run_id': 'shared'})
            lock.unlink()
            lock.symlink_to(self.lab.lock_path)
            with self.assertRaises(OSError):
                native_probe({'run_id': 'linked'})
            probe.assert_not_called()

    def test_v01_access_only_copies_preserve_identity_and_source(self):
        """RT 缺省和空值分别发布，原完整材料及身份保持一致。

        :return: 无。
        """
        before = copy.deepcopy(self.document)
        for empty in (False, True):
            result = access_document(self.document, empty)
            self.assertEqual(bool(result['token'].get('refresh_token')), False)
            self.assertEqual('refresh_token' in result['token'], empty)
            self.assertEqual(result['id_token_email'], self.document['id_token_email'])
            self.assertEqual(result['token']['access_token'], self.document['token']['access_token'])
        self.assertEqual(self.document, before)
        self.assertTrue(self.lab.publish(1, self.destination))
        self.assertEqual(self.destination.stat().st_mode & 0o777, 0o600)

    def test_v02_malformed_native_documents_fail_without_rewriting(self):
        """坏文件、缺有效期和错类型保持受控错误及原文件内容。

        :return: 无。
        """
        for value in (None, [], {}, {'auth_method': 'consumer', 'token': None}):
            with self.assertRaises(ValueError):
                native_document(value)
        for key, value in (('expiry', None), ('expiry', '2030-01-01'),
                           ('access_token', ''), ('refresh_token', True)):
            document = copy.deepcopy(self.document)
            document['token'][key] = value
            with self.assertRaises(ValueError):
                native_document(document)
        original = self.lab.path.read_bytes()
        self.lab.path.write_text('{')
        damaged = self.lab.path.read_bytes()
        with self.assertRaises(ValueError):
            self.lab.snapshot()
        self.assertEqual(self.lab.path.read_bytes(), damaged)
        self.lab.path.write_bytes(original)

    def test_v02_private_file_rejects_shared_permissions_and_symlinks(self):
        """权限扩大和符号链接不能读取为权威凭据。

        :return: 无。
        """
        self.lab.path.chmod(0o644)
        with self.assertRaises(ValueError):
            self.lab.snapshot()
        self.lab.path.chmod(0o600)
        link = self.root / 'link'
        link.symlink_to(self.lab.path)
        with self.assertRaises(OSError):
            private_json(link)

    def test_v03_file_replacement_does_not_rewrite_cached_process(self):
        """常驻进程模型在文件换代后继续使用已读取的合成 AT。

        :return: 无。
        """
        worker = self._worker()
        self.assertEqual(self.lab.refresh(1, self.endpoint), 2)
        self.assertTrue(self.lab.publish(2, self.destination))
        self.assertEqual(private_json(self.destination)['token']['access_token'], 'synthetic-at-2')
        self._send(worker, {'action': 'start', 'owner': 'one', 'call': 'call-1'})
        reply = self._send(worker, {'action': 'result', 'owner': 'one', 'call': 'call-1',
            'expected': 'synthetic-at-1'})
        self.assertTrue(reply['uses_original'])

    def test_v04_concurrent_instances_issue_one_refresh(self):
        """多个实验管理实例争用同一文件锁，只提交一次有效刷新。

        :return: 无。
        """
        barrier = threading.Barrier(6)

        def refresh():
            """同时触发六个旧代调用。"""
            lab = CredentialLab(self.lab.root)
            barrier.wait(3)
            return lab.refresh(1, self.endpoint)

        with ThreadPoolExecutor(max_workers=6) as pool:
            generations = list(pool.map(lambda _: refresh(), range(6)))
        self.assertEqual(generations, [2] * 6)
        self.assertEqual(self.server.calls, 1)
        self.assertEqual(self.lab.snapshot()['document']['token']['refresh_token'], 'synthetic-rt-2')

    def test_v05_old_receipt_cannot_publish_after_rotation(self):
        """轮换后迟到的旧代发布失败，工作副本保持新 AT。

        :return: 无。
        """
        self.assertTrue(self.lab.publish(1, self.destination))
        self.lab.refresh(1, self.endpoint)
        self.assertTrue(self.lab.publish(2, self.destination))
        current = self.destination.read_bytes()
        self.assertFalse(self.lab.publish(1, self.destination))
        self.assertEqual(self.destination.read_bytes(), current)
        self.assertEqual(self.lab.refresh(1, self.endpoint), 2)
        self.assertEqual(self.server.calls, 1)

    def test_v05_refresh_response_without_new_rt_preserves_current_rt(self):
        """OAuth 响应省略新 RT 时保留当前权威刷新材料。

        :return: 无。
        """
        self.server.mode = 'same-refresh'
        self.lab.refresh(1, self.endpoint)
        self.assertEqual(self.lab.snapshot()['document']['token']['refresh_token'], 'synthetic-rt-1')

    def test_v06_uncertain_refresh_is_not_replayed_after_restart(self):
        """服务端轮换后断连，恢复实例保留待对账及原操作。

        :return: 无。
        """
        for mode in ('disconnect', 'malformed'):
            with self.subTest(mode=mode):
                lab = CredentialLab(self.root / mode, self.document)
                self.server.expected = 'synthetic-rt-1'
                self.server.mode = mode
                with self.assertRaisesRegex(ValueError, '待对账'):
                    lab.refresh(1, self.endpoint)
                state = lab.snapshot()
                self.assertEqual(state['phase'], 'reconcile')
                self.assertTrue(state['operation_id'])
                self.assertEqual(state['generation'], 1)
                count = self.server.calls
                restored = CredentialLab(lab.root)
                with self.assertRaisesRegex(ValueError, '待对账'):
                    restored.refresh(1, self.endpoint)
                self.assertFalse(restored.publish(1, self.destination))
                self.assertEqual(self.server.calls, count)

    def test_v06_commit_failure_preserves_pending_authority(self):
        """刷新成功而提交失败时，恢复仍关闭普通执行。

        :return: 无。
        """
        original = atomic_json

        def write(path, value, *args, **kwargs):
            """只在第一次提交新代 ready 时注入写失败。"""
            if value.get('generation') == 2 and value.get('phase') == 'ready':
                raise OSError('合成存储故障')
            return original(path, value, *args, **kwargs)

        with patch('verify_agy_credentials.atomic_json', side_effect=write):
            with self.assertRaisesRegex(ValueError, '待对账'):
                self.lab.refresh(1, self.endpoint)
        state = CredentialLab(self.lab.root).snapshot()
        self.assertEqual(state['phase'], 'reconcile')
        self.assertEqual(state['document'], self.document)
        self.assertEqual(self.server.calls, 1)

    def test_v06_process_death_keeps_durable_pending(self):
        """实际终止等待刷新响应的进程，重启保持持久待确认。

        :return: 无。
        """
        self.server.release.clear()
        script = 'from verify_agy_credentials import CredentialLab; from pathlib import Path; import sys; CredentialLab(Path(sys.argv[1])).refresh(1,sys.argv[2])'
        process = subprocess.Popen([sys.executable, '-c', script, str(self.lab.root), self.endpoint],
            cwd=Path(__file__).parent, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self._close_worker, process)
        self.assertTrue(self.server.received.wait(3))
        self.assertEqual(private_json(self.lab.path)['phase'], 'pending')
        process.kill()
        process.wait(timeout=3)
        self.server.release.set()
        restored = CredentialLab(self.lab.root)
        self.assertEqual(restored.snapshot()['phase'], 'pending')
        with self.assertRaisesRegex(ValueError, '待对账'):
            restored.refresh(1, self.endpoint)
        self.assertEqual(self.server.calls, 1)

    def test_v06_failure_after_rename_keeps_new_rt_and_operation(self):
        """新凭据已替换而落盘确认失败时，保留新 RT 与原操作标识。

        :return: 无。
        """
        original = atomic_json
        operation = []

        def write(path, value, *args, **kwargs):
            """在真实原子替换之后注入提交确认故障。"""
            if value.get('phase') == 'pending':
                operation.append(value['operation_id'])
            result = original(path, value, *args, **kwargs)
            if value.get('generation') == 2 and value.get('phase') == 'ready':
                raise OSError('合成提交确认故障')
            return result

        with patch('verify_agy_credentials.atomic_json', side_effect=write):
            with self.assertRaisesRegex(ValueError, '待对账'):
                self.lab.refresh(1, self.endpoint)
        state = CredentialLab(self.lab.root).snapshot()
        self.assertEqual(state['phase'], 'reconcile')
        self.assertEqual(state['generation'], 2)
        self.assertEqual(state['document']['token']['refresh_token'], 'synthetic-rt-2')
        self.assertEqual(state['operation_id'], operation[0])

    def test_v07_retry_is_bounded_to_current_account_and_deadline(self):
        """恢复门槛逐项约束同账号、新代、单次与原截止时间。

        :return: 无。
        """
        attempt = {'account': 'one', 'generation': 1, 'attempts': 1, 'document': _document()}
        document = _document()
        document['token']['access_token'] = 'synthetic-at-2'
        current = {'account': 'one', 'generation': 2, 'phase': 'ready', 'document': document}
        arguments = {'authentication_failed': True, 'response_started': False,
            'tool_pending': False, 'deadline': time.monotonic() + 30}
        self.assertTrue(retry_allowed(attempt, current, **arguments))
        for key, value in (('authentication_failed', False), ('response_started', True),
                           ('tool_pending', True), ('deadline', time.monotonic() - 1)):
            self.assertFalse(retry_allowed(attempt, current, **{**arguments, key: value}))
        for value in ({**current, 'account': 'two'}, {**current, 'generation': 1},
                      {**current, 'phase': 'reconcile'}):
            self.assertFalse(retry_allowed(attempt, value, **arguments))
        self.assertFalse(retry_allowed({**attempt, 'attempts': 2}, current, **arguments))
        unchanged = {**current, 'document': _document()}
        self.assertFalse(retry_allowed(attempt, unchanged, **arguments))
        expired = copy.deepcopy(current)
        expired['document']['token']['expiry'] = '1970-01-01T00:00:00Z'
        self.assertFalse(retry_allowed(attempt, expired, **arguments))
        damaged = copy.deepcopy(current)
        damaged['document']['token'].pop('expiry')
        self.assertFalse(retry_allowed(attempt, damaged, **arguments))

    def test_v08_started_stream_retains_worker_until_cancel(self):
        """模拟流首包后换代，原进程持续存活直到明确停止。

        :return: 无。
        """
        worker = self._worker()
        chunk = self._send(worker, {'action': 'start', 'owner': 'one', 'call': 'stream-1'})
        self.assertEqual(chunk['event'], 'chunk')
        self.lab.refresh(1, self.endpoint)
        self.lab.publish(2, self.destination)
        self.assertIsNone(worker.poll())
        self.assertEqual(self._send(worker, {'action': 'stop'}), {'event': 'stopped', 'pending': True})
        self.assertEqual(worker.wait(timeout=3), 0)

    def test_v09_tool_result_stays_with_original_call_and_owner(self):
        """换代后跨调用方回填被拒绝，原调用真实文件效果仅发生一次。

        :return: 无。
        """
        worker = self._worker()
        self._send(worker, {'action': 'start', 'owner': 'one', 'call': 'tool-1'})
        self.lab.refresh(1, self.endpoint)
        self.lab.publish(2, self.destination)
        for owner, call in (('two', 'tool-1'), ('one', 'other')):
            self.assertEqual(self._send(worker, {'action': 'result', 'owner': owner,
                'call': call, 'expected': 'synthetic-at-1'})['event'], 'rejected')
        reply = self._send(worker, {'action': 'result', 'owner': 'one',
            'call': 'tool-1', 'expected': 'synthetic-at-1'})
        self.assertEqual(reply, {'event': 'complete', 'uses_original': True})
        self.assertEqual(self._send(worker, {'action': 'result', 'owner': 'one',
            'call': 'tool-1', 'expected': 'synthetic-at-1'})['event'], 'rejected')
        self.assertEqual((self.root / 'effects').read_text().splitlines(), ['effect'])

    def test_v10_stopping_one_worker_does_not_stop_new_generation(self):
        """旧进程取消后的关闭保持新代权威材料和工作文件。

        :return: 无。
        """
        worker = self._worker()
        self.lab.refresh(1, self.endpoint)
        self.lab.publish(2, self.destination)
        current = self.destination.read_bytes()
        self._send(worker, {'action': 'stop'})
        self.assertEqual(worker.wait(timeout=3), 0)
        self.assertEqual(self.destination.read_bytes(), current)
        self.assertEqual(self.lab.snapshot()['generation'], 2)


if __name__ == '__main__':
    unittest.main()
