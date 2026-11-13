"""隔离TLS模拟接收端，回显独立请求标记。"""
import json
from http.server import BaseHTTPRequestHandler
from uuid import uuid4

POSTS = []


class Upstream(BaseHTTPRequestHandler):
    """回显请求标记并收集原生发送身份。"""

    def log_message(self, *_args):
        """抑制默认日志。@param _args 日志参数。@return 无。"""

    def do_POST(self):
        """记录单次请求并返回对应标记。@return 无。"""
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        marker = next((str(m['content']) for m in body['messages'] if m['role'] == 'user' and 'clone-request-' in str(m['content'])), '')
        POSTS.append({'marker': marker, 'client_request_id': self.headers.get('x-client-request-id'),
                      'metadata': body.get('metadata'), 'model': body['model']})
        content = json.dumps({'id': 'msg_' + uuid4().hex, 'type': 'message', 'role': 'assistant',
                             'model': body['model'], 'content': [{'type': 'text', 'text': marker}],
                             'stop_reason': 'end_turn', 'usage': {'input_tokens': 1, 'output_tokens': 1}}).encode()
        self.send_response(200)
        self.send_header('content-type', 'application/json')
        self.send_header('content-length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)
