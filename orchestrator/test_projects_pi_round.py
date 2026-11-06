"""真实 Python 父进程到 Pi SDK 的单目标收尾管道验证，上游仅本地替身。"""
import json
import shutil
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from projects import AGENT_GUIDE, TOOLS
from projects_pi import ProjectsPi, diagnose_stream_failure


HOST = Path(__file__).resolve().parents[1] / 'images/pi-agent/host.mjs'


@unittest.skipUnless(shutil.which('node') and (HOST.parent / 'node_modules/@earendil-works/pi-coding-agent/package.json').is_file(),
    '当前环境未安装固定 Pi SDK；完整管道需在具备依赖的环境执行')
class PiRoundPipeTests(unittest.TestCase):
    """使用真实子进程和 SDK，确认通过结果持久化后无需再调用上游。"""

    def test_parent_delivers_success_and_receives_normal_completion(self):
        """通过结果沿真实管道进入原生会话，父进程按 settled 正常退出。:return: None。"""
        self.verify_round('project_submit', {'summary': '本地合成交付'},
            {'status': 'passed', 'submission_id': 'verified-pipe-result', 'round_complete': True})

    def test_unexpected_exit_is_recoverable_only_after_valid_ready(self):
        """真实子进程退出可恢复，坏协议和未就绪退出不伪装成模型断流。:return: None。"""
        for mode, reason, code in (
                ('ready', 'model_unavailable', 'controller_interrupted'),
                ('protocol', 'provider_request_error', 'pi_protocol_error'),
                ('initialization', 'provider_request_error', 'pi_initialization')):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                driver = Path(directory) / 'exit.mjs'
                output = '' if mode == 'initialization' else json.dumps({'type': 'ready', 'session_file': str(Path(directory) / 'original.jsonl')}) + '\n'
                if mode == 'protocol':
                    output += 'invalid-json\n'
                driver.write_text("process.stdin.once('data', () => process.stdout.write("
                    + json.dumps(output) + ", () => process.exit(3)));\n")
                events = []
                pi = ProjectsPi(driver)
                with patch.object(pi, 'available', return_value=True):
                    outcome = pi.run({'session_dir': directory}, lambda *_: self.fail('不能执行工具'),
                        events.append, threading.Event(), 5)
                self.assertEqual('error', outcome)
                self.assertEqual(reason, events[-1]['reason'])
                self.assertEqual(code, events[-1]['code'])

    def test_cancelled_ready_exit_never_schedules_recovery(self):
        """取消优先于同时到达的退出事件，不能自行重启用户已停止的控制者。:return: None。"""
        with tempfile.TemporaryDirectory() as directory:
            driver = Path(directory) / 'cancel.mjs'
            driver.write_text("process.stdin.once('data', () => process.stdout.write("
                + json.dumps(json.dumps({'type': 'ready'}) + '\n') + ", () => process.exit(3)));\n")
            stop, events = threading.Event(), []

            def receive(event):
                """收到已就绪事件即模拟用户取消。:param event: 子进程事件。:return: None。"""
                events.append(event)
                stop.set()

            pi = ProjectsPi(driver)
            with patch.object(pi, 'available', return_value=True):
                outcome = pi.run({'session_dir': directory}, lambda *_: None, receive, stop, 5)
            self.assertEqual('stopped', outcome)
            self.assertFalse(any(event['type'] == 'error' for event in events))

    def test_startup_failure_is_persisted_before_handing_back_without_more_model_requests(self):
        """真实 Python／Node 管道保存故障回执后结束，不追加一次模型解释。:return: None。"""
        self.verify_round('claude_start', {'project_key': 'example', 'objective_id': 'feature'},
            {'status': 'rejected', 'controller_yield': True, 'failure': {'code': 'python_incompatible'}})

    def verify_round(self, tool_name, arguments, result):
        """驱动真实 SDK 与父进程交接一个工具结果。

        :param tool_name: 本次调用的真实工具。
        :param arguments: 工具参数。
        :param result: 控制端返回的交接事实。
        :return: None。
        """
        requests, tools, events = [], [], []

        class Handler(BaseHTTPRequestHandler):
            """只接受本地合成 OpenAI 流式请求的替身。"""

            def do_POST(self):
                """记录合成请求并返回确定的工程交付工具调用。:return: None。"""
                body = self.rfile.read(int(self.headers['Content-Length']))
                requests.append(json.loads(body))
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                delta = {'role': 'assistant', 'tool_calls': [{'index': 0, 'id': 'local-submission', 'type': 'function',
                    'function': {'name': tool_name, 'arguments': json.dumps(arguments)}}]}
                chunks = [
                    {'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]},
                    {'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'tool_calls'}]},
                    {'choices': [], 'usage': {'prompt_tokens': 11, 'completion_tokens': 7, 'total_tokens': 18}},
                ]
                for chunk in chunks:
                    value = {'id': 'local-pipe', 'object': 'chat.completion.chunk', 'model': 'local-test', **chunk}
                    self.wfile.write(('data: ' + json.dumps(value) + '\n\n').encode())
                self.wfile.write(b'data: [DONE]\n\n')

            def log_message(self, format, *args):
                """测试仅保存断言事实，不输出 HTTP 请求日志。:param format: 格式。:param args: 参数。:return: None。"""
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def execute(name, args, call_id):
            """返回控制端已接受的合成交付事实。:param name: 工具。:param args: 参数。:param call_id: 操作标识。:return: 完成事实。"""
            tools.append((name, args, call_id))
            return result

        try:
            with tempfile.TemporaryDirectory() as directory:
                configuration = {'session_dir': directory, 'base_url': f'http://127.0.0.1:{server.server_port}/v1',
                    'api_key': 'synthetic-local-pipe-key', 'models': ['local-test'], 'timeout_sec': 20,
                    'instructions': AGENT_GUIDE + '\n本次使用本地合成验收，不请求真实账号。',
                    'prompt': '验证本地管道。', 'context_mode': 'fresh', 'tools': TOOLS}
                outcome = ProjectsPi(HOST).run(configuration, execute, events.append, threading.Event(), 20)
                self.assertEqual('settled', outcome)
                self.assertEqual(1, len(requests))
                self.assertEqual({tool['name'] for tool in TOOLS},
                    {tool['function']['name'] for tool in requests[0]['tools']})
                self.assertEqual(1, len(tools))
                self.assertEqual((tool_name, arguments, 'local-submission'), tools[0])
                self.assertEqual(1, sum(event['type'] == 'settled' for event in events))
                session = next(event['session_file'] for event in events if event['type'] == 'ready')
                entries = [json.loads(line) for line in Path(session).read_text().splitlines()]
                delivered = next(entry['message'] for entry in entries
                    if entry.get('message', {}).get('role') == 'toolResult')
                self.assertEqual(result, json.loads(delivered['content'][0]['text']))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)


class PiSessionDiagnosisTests(unittest.TestCase):
    """旧错误仅凭受管会话的完整、近期失败记录建立恢复资格。"""

    def test_diagnosis_reads_bounded_tail_and_rejects_mismatched_evidence(self):
        """大历史不会全量载入，成功尾消息、坏时间、错误目录及残缺行不能解锁。:return: None。"""
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = directory / 'original.jsonl'
            now = datetime.now(timezone.utc)
            header = {'type': 'session', 'id': 'original-pi', 'cwd': str(directory)}
            failure = {'type': 'message', 'timestamp': now.isoformat(), 'message': {'role': 'assistant',
                'provider': 'projects', 'stopReason': 'error', 'errorMessage': 'Stream ended without finish_reason'}}
            history = json.dumps({'type': 'message', 'message': {'role': 'user', 'content': 'x' * 800000}}) + '\n'
            text = json.dumps(header) + '\n' + history + json.dumps(failure) + '\n'
            path.write_text(text)
            self.assertEqual('stream_incomplete', diagnose_stream_failure(directory, str(path), now.timestamp()))
            self.assertIsNone(diagnose_stream_failure(directory, str(path), now.timestamp() + 6))
            for value in (False, None, 123, 'not-a-date'):
                changed = {**failure, 'timestamp': value}
                path.write_text(json.dumps(header) + '\n' + json.dumps(changed) + '\n')
                self.assertIsNone(diagnose_stream_failure(directory, str(path), now.timestamp()))
            path.write_text(text + json.dumps({'type': 'message', 'message': {'role': 'assistant', 'stopReason': 'stop'}}) + '\n')
            self.assertIsNone(diagnose_stream_failure(directory, str(path), now.timestamp()))
            path.write_text(text.rstrip('\n'))
            self.assertIsNone(diagnose_stream_failure(directory, str(path), now.timestamp()))
            path.write_text(json.dumps({**header, 'cwd': '/another-account'}) + '\n' + json.dumps(failure) + '\n')
            self.assertIsNone(diagnose_stream_failure(directory, str(path), now.timestamp()))
            path.write_text(text)
            alias = directory / 'linked.jsonl'
            alias.symlink_to(path)
            self.assertIsNone(diagnose_stream_failure(directory, str(alias), now.timestamp()))


if __name__ == '__main__':
    unittest.main()
