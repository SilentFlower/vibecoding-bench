"""容器内的真实Claude会话续跑夹具，所有模型响应来自本机合成上游。"""
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class FixtureHandler(BaseHTTPRequestHandler):
    """仅处理真实CLI的本地协议请求并返回Read工具响应。"""

    def log_message(self, *arguments) -> None:
        """关闭夹具访问日志。:param arguments: HTTP日志参数。:return: None。"""

    def do_GET(self) -> None:
        """提供合成模型目录。:return: None。"""
        self._json({'data': [{'id': 'claude-sonnet-4-6', 'type': 'model', 'display_name': 'Fixture'}]})

    def _json(self, body: dict) -> None:
        content = json.dumps(body).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:
        """按本轮用户输入安排一次实际Read，再回显真实工具结果。:return: None。"""
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))))
        if 'count_tokens' in self.path:
            self._json({'input_tokens': 100})
            return
        if not self.path.startswith('/v1/messages'):
            self._json({})
            return
        self.server.requests += 1
        messages = body.get('messages', [])
        selected = None
        for index, message in enumerate(messages):
            content = message.get('content', [])
            texts = [content] if isinstance(content, str) else [item.get('text', '') for item in content if item.get('type') == 'text']
            for text in texts:
                match = re.search(r'SCRATCHPAD_TEST_PATH=(\S+)\s+TURN=(\S+)', text)
                if match:
                    selected = (index, match.group(1), match.group(2))
        if selected is None:
            self.send_error(400, 'fixture prompt missing')
            return
        index, path, turn = selected
        tool_id = 'tool_fixture_' + hashlib.sha256(turn.encode()).hexdigest()[:16]
        result = None
        for message in messages[index + 1:]:
            content = message.get('content', [])
            if isinstance(content, list):
                for item in content:
                    if item.get('type') == 'tool_result' and item.get('tool_use_id') == tool_id:
                        result = item.get('content', '')
        if result is None:
            block = {'type': 'tool_use', 'id': tool_id, 'name': 'Read', 'input': {'file_path': path}}
            stop = 'tool_use'
        else:
            block = {'type': 'text', 'text': '实际读取结果：' + (result if isinstance(result, str) else json.dumps(result, ensure_ascii=False))}
            stop = 'end_turn'
        message = {'id': 'msg_' + tool_id, 'type': 'message', 'role': 'assistant',
            'model': body.get('model', 'claude-sonnet-4-6'), 'content': [block],
            'stop_reason': stop, 'stop_sequence': None, 'usage': {'input_tokens': 100, 'output_tokens': 20}}
        if not body.get('stream'):
            self._json(message)
            return
        start = {**message, 'content': [], 'stop_reason': None, 'usage': {'input_tokens': 100, 'output_tokens': 0}}
        first = {'type': 'text', 'text': ''} if block['type'] == 'text' else {**block, 'input': {}}
        delta = {'type': 'text_delta', 'text': block['text']} if block['type'] == 'text' else {
            'type': 'input_json_delta', 'partial_json': json.dumps(block['input'])}
        events = [('message_start', {'type': 'message_start', 'message': start}),
            ('content_block_start', {'type': 'content_block_start', 'index': 0, 'content_block': first}),
            ('content_block_delta', {'type': 'content_block_delta', 'index': 0, 'delta': delta}),
            ('content_block_stop', {'type': 'content_block_stop', 'index': 0}),
            ('message_delta', {'type': 'message_delta', 'delta': {'stop_reason': stop, 'stop_sequence': None}, 'usage': {'output_tokens': 20}}),
            ('message_stop', {'type': 'message_stop'})]
        content = ''.join('event: ' + event + '\ndata: ' + json.dumps(value) + '\n\n' for event, value in events).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def main() -> None:
    """运行一次新会话或原会话恢复，输出精简验证事实。:return: None。"""
    binary, session, path, turn, mode = sys.argv[1:]
    home = Path('/home/node')
    (home / '.claude').mkdir(exist_ok=True)
    (home / '.claude.json').write_text(json.dumps({'hasCompletedOnboarding': True}))
    cwd = home / 'projects/fixture'
    cwd.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)
    server.requests = 0
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    environment = {**os.environ, 'HOME': str(home), 'ANTHROPIC_API_KEY': 'synthetic-local-fixture',
        'ANTHROPIC_BASE_URL': 'http://127.0.0.1:' + str(server.server_port),
        'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC': '1', 'DISABLE_TELEMETRY': '1', 'DISABLE_AUTOUPDATER': '1'}
    command = [binary, '-p', 'SCRATCHPAD_TEST_PATH=' + path + ' TURN=' + turn,
        '--resume' if mode == 'resume' else '--session-id', session, '--output-format', 'json',
        '--model', 'sonnet', '--tools', 'Read', '--dangerously-skip-permissions']
    try:
        result = subprocess.run(command, cwd=cwd, env=environment, capture_output=True, text=True, timeout=90)
        if result.returncode:
            raise ValueError('真实CLI夹具执行失败：' + result.stderr[-1500:] + result.stdout[-1500:])
        response = json.loads(result.stdout)
        print(json.dumps({'session_id': response.get('session_id'), 'result': response.get('result'),
            'requests': server.requests, 'is_error': response.get('is_error')}, ensure_ascii=False))
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
