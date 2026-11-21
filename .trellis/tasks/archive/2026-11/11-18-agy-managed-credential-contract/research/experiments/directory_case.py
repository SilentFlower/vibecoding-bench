"""读取实际模型目录的字段和模型标识。"""
MODEL_REQUEST_LIMIT = 0
connection = HTTPConnection('127.0.0.1', PORT, timeout=15)
connection.request('POST', '/exa.language_server_pb.LanguageServerService/GetAvailableModels',
    b'{"forceRefresh":true}', {'Content-Type': 'application/json', 'x-codeium-csrf-token': CSRF})
response = connection.getresponse()
value = json.loads(response.read())
root = value.get('response')
if isinstance(root, str):
    try:
        root = json.loads(root)
    except ValueError:
        pass
found = [{'id': key, 'model': item.get('model'), 'api_provider': item.get('apiProvider'),
    'model_provider': item.get('modelProvider')} for key, item in root['models'].items() if '3.8' in key]
print(json.dumps({'status': response.status, 'response_type': type(root).__name__,
    'top_fields': list(root) if isinstance(root, dict) else [], 'matches': found[:30]}))
