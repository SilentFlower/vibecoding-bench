"""以独立原生进程验证异常凭据文件，并读取账号状态的字段摘要。"""
MODEL_REQUEST_LIMIT = 0

import copy
import os
import re
import subprocess
from pathlib import Path

path = Path('/home/agy/.gemini/antigravity-cli/antigravity-oauth-token')
original = json.loads(path.read_text())
results = []
try:
    for mode in ['expired', 'missing-expiry', 'bad-json', 'identity-label']:
        document = copy.deepcopy(original)
        if mode == 'expired':
            document['token']['expiry'] = '1970-01-01T00:00:00Z'
        elif mode == 'missing-expiry':
            document['token'].pop('expiry', None)
        elif mode == 'identity-label':
            document['id_token_email'] = 'other-fixture@example.test'
        payload = '{' if mode == 'bad-json' else json.dumps(document)
        pending = path.with_suffix('.pending')
        pending.write_text(payload)
        pending.chmod(0o600)
        pending.replace(path)
        try:
            result = subprocess.run(['/opt/native/agy', 'models'], capture_output=True, timeout=15)
            content = (result.stdout + result.stderr).lower()
            for name, value in [('stdout', result.stdout), ('stderr', result.stderr)]:
                target = Path('/workspace') / (mode + '.' + name)
                descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, 'wb') as output:
                    output.write(value)
            results.append({'mode': mode, 'exit_code': result.returncode,
                'model_names_present': b'gemini-' in content,
                'expired_token_error': b'token expired' in content,
                'missing_refresh_error': b'refresh token' in content,
                'json_error': b'json' in content})
        except subprocess.TimeoutExpired:
            results.append({'mode': mode, 'status': 'timeout'})
finally:
    pending = path.with_suffix('.restore')
    pending.write_text(json.dumps(original))
    pending.chmod(0o600)
    pending.replace(path)

connection = HTTPConnection('127.0.0.1', PORT, timeout=15)
connection.request('POST', '/exa.language_server_pb.LanguageServerService/GetUserStatus', b'{}',
    {'Content-Type': 'application/json', 'x-codeium-csrf-token': CSRF})
response = connection.getresponse()
value = json.loads(response.read())
connection.close()
target = Path('/workspace/user-status.json')
descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, 'w') as output:
    json.dump(value, output)
fields = {}
for key, item in value.items():
    if isinstance(item, dict) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', key):
        fields[key] = [name for name in item if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', name)]
print(json.dumps({'evidence': 'native_oauth', 'scope': 'native_credential_faults',
    'model_submissions': 0, 'cases': results, 'user_status_http_status': response.status,
    'user_status_fields': list(value), 'nested_status_fields': fields}))
