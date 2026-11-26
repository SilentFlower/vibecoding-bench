"""以回环私有 HTTP 模拟 sender，验证网关的签名修复、凭据重试及 V1 工具续轮。"""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    """提供受控的绑定、能力和原生提交响应。"""
    records = []
    oauth_releases = {}

    def log_message(self, *_args):
        """保持合成请求正文私有。@param _args 默认日志参数。@return None。"""

    def reply(self, status, value, headers=None):
        """返回固定JSON。@param status HTTP状态。@param value 合成载荷。@param headers 附加头。@return None。"""
        raw = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('content-type', 'application/json')
        self.send_header('content-length', str(len(raw)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        """读取合成绑定及能力。@return None。"""
        base = f'http://127.0.0.1:{self.server.server_port}'
        environment = 'a' * 32
        if self.path.startswith('/internal/v3/transport/'):
            account = int(self.path.rsplit('/', 1)[1].split('?')[0])
            deployment = hashlib.sha256(b'native-repair-fixture').hexdigest()[:12]
            self.reply(200, {'account_id': account, 'environment_id': environment, 'generation': 1,
                'endpoint': f'{base}/cluster-transports/v2/{deployment}/' + 'b' * 32 + f'/{environment}/1',
                'secret': 'synthetic-private-secret' * 2, 'release_id': 'native-repair-fixture'})
        elif self.path.endswith('/internal/native/status'):
            self.reply(200, {'raw_input_protocol': 1, 'environment_id': environment, 'generation': 1,
                'versions': {'2.1.293': {'available': True}}})
        elif self.path == '/observations':
            self.reply(200, self.records)
        elif self.path.startswith('/oauth-release/'):
            release = self.oauth_releases.get(self.path.rsplit('/', 1)[1])
            if release is None:
                self.reply(404, {})
            else:
                release.set()
                self.reply(200, {})
        else:
            self.reply(404, {})

    def do_POST(self):
        """每个内部提交模拟一次供应商响应。@return None。"""
        submission = json.loads(self.rfile.read(int(self.headers['content-length'])))
        body = submission['input']['body']
        labels = [message.get('content') for message in body['messages'] if isinstance(message.get('content'), str)]
        tools_returned = any(block.get('type') == 'tool_result' for message in body['messages']
            if isinstance(message.get('content'), list) for block in message['content'])
        signed = any(block.get('type') in ('thinking', 'redacted_thinking') for message in body['messages']
            if isinstance(message.get('content'), list) for block in message['content'])
        request_id = submission['request']['request_id']
        oauth_case = next((label for label in labels if label.startswith('oauth-')), None)
        bearer_kind = {'synthetic-oauth-old': 'old', 'synthetic-oauth-new': 'new',
            'synthetic-oauth-backup': 'backup'}.get(submission['bearer'])
        release = None
        if oauth_case and oauth_case not in ('oauth-unchanged', 'oauth-revoked-current',
                'oauth-revoked-no-observation', 'oauth-revoked-oversize') and bearer_kind == 'old':
            release = self.oauth_releases[request_id] = threading.Event()
        self.records.append({'account_id': submission['request']['account_id'], 'id': request_id,
            'version': submission.get('source_version', '2.1.293'), 'body': body, 'bearer_kind': bearer_kind})
        observation = {'schema_version': 1, 'source_version': submission.get('source_version', '2.1.293'),
            'parameters': {'model': body['model'], 'stream': body.get('stream'), 'max_tokens': body.get('max_tokens')},
            'session_id': json.loads(body.get('metadata', {}).get('user_id', '{}')).get('session_id')
                or submission['input'].get('context', {}).get('sessionId'),
            'previous_message_id': None, 'body_sha256': hashlib.sha256(json.dumps(body).encode()).hexdigest()}
        headers = {'x-v3-native-observation': base64.b64encode(json.dumps(observation).encode()).decode(),
            'request-id': f'req_fixture_{len(self.records)}'}
        if release is not None and not release.wait(5):
            self.reply(500, {'error': {'message': '测试未释放首发'}}, headers)
            return
        if 'budget-exhausted' in labels or oauth_case == 'oauth-budget':
            time.sleep(1.2)
        revoked = {'type': 'error', 'error': {'type': 'authentication_error',
            'message': 'OAuth access token has been revoked.'}}
        if oauth_case == 'oauth-revoked-no-observation' and bearer_kind == 'old':
            self.reply(401, revoked, {'request-id': headers['request-id']})
        elif oauth_case == 'oauth-revoked-oversize' and bearer_kind == 'old':
            self.reply(401, {**revoked, 'padding': 'x' * 4096}, headers)
        elif oauth_case and oauth_case.startswith('oauth-revoked-') and (
                bearer_kind == 'old' or oauth_case == 'oauth-revoked-repeated' and bearer_kind == 'new'):
            self.reply(401, revoked, headers)
        elif oauth_case == 'oauth-revoked-limited' and bearer_kind == 'new':
            self.reply(429, {'type': 'error', 'error': {'type': 'rate_limit_error',
                'message': 'synthetic capacity rejection'}}, {**headers, 'retry-after': '60'})
        elif 'native-account-forbidden' in labels and bearer_kind != 'backup':
            self.reply(403, {'type': 'error', 'error': {'type': 'permission_error',
                'message': 'This account has been disabled.'}}, headers)
        elif oauth_case == 'oauth-unobserved':
            self.reply(401, {'error': {'type': 'authentication_error'}}, {'request-id': headers['request-id']})
        elif oauth_case == 'oauth-bare':
            self.reply(401, {}, headers)
        elif oauth_case == 'oauth-other':
            self.reply(401, {'error': {'type': 'invalid_request_error'}}, headers)
        elif oauth_case and not oauth_case.startswith('oauth-revoked-') and (
                bearer_kind != 'new' or oauth_case == 'oauth-repeated'):
            self.reply(401, {'error': {'type': 'authentication_error', 'message': '合成凭据失效'}}, headers)
        elif 'transport-failure' in labels:
            self.reply(502, {}, {'x-v3-transport-error': 'unknown'})
        elif 'ordinary-400' in labels:
            self.reply(400, {'error': {'type': 'invalid_request_error', 'message': 'max_tokens invalid'}}, headers)
        elif 'rate-limit' in labels:
            self.reply(429, {'error': {'type': 'rate_limit_error', 'message': 'synthetic credit rejection'}}, headers)
        elif signed or 'always-signature' in labels:
            self.reply(400, {'error': {'type': 'invalid_request_error', 'message': 'Invalid signature in thinking block'}}, headers)
        elif 'v1-receipt-fixture' in labels and not tools_returned:
            self.reply(200, {'id': 'msg_fixture', 'type': 'message', 'role': 'assistant', 'model': body['model'],
                'content': [{'type': 'tool_use', 'id': f'toolu_{request_id}', 'name': 'Read', 'input': {'path': 'fixture'}}],
                'stop_reason': 'tool_use', 'usage': {'input_tokens': 2, 'output_tokens': 1}}, headers)
        else:
            self.reply(200, {'id': 'msg_fixture', 'type': 'message', 'role': 'assistant', 'model': body['model'],
                'content': [{'type': 'text', 'text': '合成成功'}], 'stop_reason': 'end_turn', 'usage': {'input_tokens': 2, 'output_tokens': 1}}, headers)


def main():
    """启动回环服务后仅执行对应Rust回归。@return 测试进程退出码。"""
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    env = {**os.environ, 'V3_RUNTIME_URL': f'http://127.0.0.1:{server.server_port}',
        'V3_INTERNAL_TOKEN': 'synthetic-control-token' * 2, 'V3_DEPLOYMENT_ID': 'native-repair-fixture',
        'V3_RELEASE': 'native-repair-fixture', 'V3_UPDATE_GATE_DIR': '', 'FLOWER_SIGNATURE_FIXTURE': '1'}
    try:
        return subprocess.run(['cargo', 'test', '--locked', '--lib', '--', '--ignored', '--nocapture', '--test-threads=1',
            'native_signature_repair_gateway_roundtrip', 'native_v1_receipt_gateway_roundtrip'],
            cwd=Path(__file__).resolve().parents[1], env=env).returncode
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    raise SystemExit(main())
