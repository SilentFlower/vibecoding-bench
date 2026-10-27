"""真实 Python 父进程到 Pi SDK 的单目标收尾管道验证，上游仅本地替身。"""
import json
import shutil
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from projects import AGENT_GUIDE, TOOLS
from projects_pi import ProjectsPi


HOST = Path(__file__).resolve().parents[1] / 'images/pi-agent/host.mjs'


@unittest.skipUnless(shutil.which('node') and (HOST.parent / 'node_modules/@earendil-works/pi-coding-agent/package.json').is_file(),
    '当前环境未安装固定 Pi SDK；完整管道需在具备依赖的环境执行')
class PiRoundPipeTests(unittest.TestCase):
    """使用真实子进程和 SDK，确认通过结果持久化后无需再调用上游。"""

    def test_parent_delivers_success_and_receives_normal_completion(self):
        """通过结果沿真实管道进入原生会话，父进程按 settled 正常退出。:return: None。"""
        self.verify_round('project_submit', {'summary': '本地合成交付'},
            {'status': 'passed', 'submission_id': 'verified-pipe-result', 'round_complete': True})

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


if __name__ == '__main__':
    unittest.main()
