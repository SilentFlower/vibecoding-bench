"""以回环私有 sender 验证 native 的429分类、换号及原请求截止。"""

import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
from http.server import ThreadingHTTPServer

from native_signature_fixture import Handler


class RateLimitHandler(Handler):
    """复用隔离绑定协议，为每次原生提交提供确定的限流响应。"""

    records = []

    def do_POST(self):
        """按场景返回明确429或成功，并记录实际提交身份。@return None。"""
        submission = json.loads(self.rfile.read(int(self.headers['content-length'])))
        body = submission['input']['body']
        label = body['messages'][0]['content']
        account_id = submission['request']['account_id']
        previous = sum(record['label'] == label and record['account_id'] == account_id
                       for record in self.records)
        primary = submission['bearer'].startswith('synthetic-primary-')
        self.records.append({'label': label, 'account_id': account_id,
                             'id': submission['request']['request_id'],
                             'version': submission.get('source_version', '2.1.293'),
                             'device_id': submission['device_id'], 'body': body})
        observation = {'schema_version': 1, 'source_version': submission.get('source_version', '2.1.293'),
                       'parameters': {'model': body['model'], 'stream': body.get('stream'),
                                      'max_tokens': body.get('max_tokens')},
                       'session_id': json.loads(body['metadata']['user_id'])['session_id'],
                       'previous_message_id': None,
                       'body_sha256': hashlib.sha256(json.dumps(body).encode()).hexdigest()}
        headers = {'x-v3-native-observation': base64.b64encode(json.dumps(observation).encode()).decode(),
                   'request-id': f'req_rate_limit_{len(self.records)}'}
        if label.startswith('unknown-'):
            self.reply(502, {}, {'x-v3-transport-error': 'unknown'})
            return
        if label.startswith('business-'):
            self.reply(429, {'type': 'error', 'error': {'type': 'rate_limit_error',
                                                       'message': 'long context requires usage credits'}}, headers)
            return
        if label.startswith('signature-capacity-') and any(
                block.get('type') in ('thinking', 'redacted_thinking')
                for message in body['messages'] if isinstance(message.get('content'), list)
                for block in message['content']):
            self.reply(400, {'error': {'type': 'invalid_request_error',
                                      'message': 'Invalid signature in thinking block'}}, headers)
            return
        rejected = (label.startswith(('capacity-', 'fable-', 'restricted-', 'signature-capacity-')) and primary
                    or label.startswith(('deadline-', 'exhausted-', 'cancel-'))
                    or label.startswith('transient-') and primary and previous == 0)
        if rejected:
            if label.startswith(('capacity-', 'exhausted-', 'restricted-', 'signature-capacity-')):
                headers['retry-after'] = '60'
            self.reply(429, {'type': 'error', 'error': {'type': 'rate_limit_error',
                                                       'message': 'synthetic capacity rejection'}}, headers)
            return
        self.reply(200, {'id': 'msg_rate_limit', 'type': 'message', 'role': 'assistant',
                         'model': body['model'], 'content': [{'type': 'text', 'text': '合成成功'}],
                         'stop_reason': 'end_turn', 'usage': {'input_tokens': 2, 'output_tokens': 1}}, headers)


def main():
    """只在独立子进程设置回环传输环境并执行对应Rust测试。@return 测试退出码。"""
    server = ThreadingHTTPServer(('127.0.0.1', 0), RateLimitHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    env = {**os.environ, 'V3_RUNTIME_URL': f'http://127.0.0.1:{server.server_port}',
           'V3_INTERNAL_TOKEN': 'synthetic-control-token' * 2, 'V3_DEPLOYMENT_ID': 'native-repair-fixture',
           'V3_RELEASE': 'native-repair-fixture', 'V3_UPDATE_GATE_DIR': '',
           'FLOWER_RATE_LIMIT_FIXTURE': '1'}
    try:
        return subprocess.run(['cargo', 'test', '--locked', '--lib', 'native_rate_limit_gateway_roundtrip',
                               '--', '--ignored', '--nocapture'],
                              cwd=Path(__file__).resolve().parents[1], env=env).returncode
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    raise SystemExit(main())
