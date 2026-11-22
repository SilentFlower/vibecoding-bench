"""在同一原生工具轮中发布不同代次的 AT，并核对真实工具归属及效果。"""
MODEL_REQUEST_LIMIT = 2
from pathlib import Path


def rpc(method, body):
    """执行原生控制调用。@param method 已存在的方法。@param body 已定义字段。@return 状态及原生结果。"""
    connection = HTTPConnection('127.0.0.1', PORT, timeout=100)
    connection.request('POST', '/exa.language_server_pb.LanguageServerService/' + method,
        json.dumps(body).encode(), {'Content-Type': 'application/json', 'x-codeium-csrf-token': CSRF})
    response = connection.getresponse()
    value = json.loads(response.read())
    connection.close()
    return response.status, value


model = 'MODEL_PLACEHOLDER_M320'
config = json.loads('{"executorConfig": {"maxGeneratorInvocations": 1, "disableEmptyOutputContinuation": true}, "plannerConfig": {"planModel": "MODEL_PLACEHOLDER_M36", "retryConfig": {"apiRetry": {"maxRetries": 0}}, "customizationConfig": {"mcpServers": [], "skipToolNamePrefix": true, "skipToolDescriptionPrefix": true}, "toolConfig": {"mcp": {"forceDisable": false, "enableLazyLoad": false, "nonBlockingTurnLoad": false}, "descriptionOverrideMap": {"toolOverrides": {"phase7_external_tool": {"argumentValueOverrides": {"toolSummary": {"omit": true}}}}}}, "declarativeMixinConfig": {"providers": [], "tools": [], "promptSections": [{"custom": {"content": "PHASE8_SYSTEM"}}], "forceDisableFundamentalComponents": true, "preInvocationHooks": [{"name": "message_delivery", "builtin": true}, {"name": "battle_mode_max_turns", "builtin": true}, {"name": "context_summary", "builtin": true}], "postInvocationHooks": [{"name": "chain_check", "builtin": true}, {"name": "message_continue_check", "builtin": true}, {"name": "no_tool_call_check", "builtin": true}, {"name": "max_generator_invocations_check", "builtin": true}], "preToolHooks": [{"name": "battle_mode_tool_args", "builtin": true}, {"name": "command_assessor", "builtin": true}, {"name": "auto_run_safety_gate", "builtin": true}, {"name": "citc_top_level_write_guard", "builtin": true}], "postToolHooks": [{"name": "stained_creds_guidance", "builtin": true}, {"name": "command_assessor", "builtin": true}], "toolDecorators": [{"name": "output_truncation", "builtin": true}]}}, "trajectoryConversionConfig": {"useRawUserMessage": true, "ignoreUserInputTimestamp": true, "disableStepId": true}}')
config["plannerConfig"]["planModel"] = model
config["plannerConfig"]["retryConfig"]["modelOutputRetry"] = {"maxRetries": 0}
config["plannerConfig"]["completionConfigOverride"] = {"maxTokens": 2048}

config["executorConfig"]["maxGeneratorInvocations"] = 2

import hmac
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

called = threading.Event()
release = threading.Event()
seen = set()
calls = []
cascade = None
fixture = Path('/workspace/sample.txt')
fixture.write_text('AGY_REAL_TOOL_RESULT_OK')
summary = {'evidence': 'native_oauth', 'scope': 'tool_wait_credential_swap',
    'reserved_generations': 2, 'tool_effect_count': 0, 'file_published_generation_2': False}


class Handler(BaseHTTPRequestHandler):
    """仅服务本轮原生调用的回环 MCP 工具端点。"""

    def log_message(self, *args):
        """静默处理访问日志。@param args 日志参数。@return 无。"""

    def do_POST(self):
        """验证原生调用归属，等待凭据发布后读取真实实验文件。@return 无。"""
        value = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        method = value.get('method')
        result = None
        if method == 'initialize':
            result = {'protocolVersion': value['params']['protocolVersion'], 'capabilities': {'tools': {}},
                'serverInfo': {'name': 'credential-contract', 'version': '1'}}
        elif method == 'tools/list':
            result = {'tools': [{'name': 'contract_read', 'description': '读取凭据实验中的样本，返回唯一标记。',
                'inputSchema': {'type': 'object', 'properties': {'key': {'type': 'string'}},
                    'required': ['key'], 'additionalProperties': False}}]}
        elif method == 'tools/call':
            params = value['params']
            metadata = params.get('_meta', {})
            record = {'conversation_matches': metadata.get('antigravity.google/conversation_id') == cascade}
            try:
                trajectory_id, index = metadata['progressToken'].rsplit(':', 1)
                status, current = rpc('GetCascadeTrajectory', {'cascadeId': cascade})
                trajectory = current['trajectory']
                call = trajectory['steps'][int(index)]['metadata']['toolCall']
                record['trajectory_matches'] = status == 200 and trajectory_id == trajectory['trajectoryId']
                record['arguments_match'] = call['name'] == params['name'] == 'contract_read' and json.loads(call['argumentsJson']) == params.get('arguments', {}) == {'key': 'sample'}
                record['new_call'] = call['id'] not in seen
                record['matched'] = all(record.values())
                if record['matched']:
                    seen.add(call['id'])
                    calls.append(record)
                    called.set()
                    if not release.wait(35):
                        raise ValueError('实验回填等待超时')
                    text = fixture.read_text()
                    with Path('/workspace/tool-effects.txt').open('a') as effects:
                        effects.write('read\n')
                    result = {'content': [{'type': 'text', 'text': text}],
                        'structuredContent': {'marker': text}, 'isError': False}
                else:
                    calls.append(record)
                    result = {'content': [{'type': 'text', 'text': '实验调用归属不匹配'}], 'isError': True}
            except Exception:
                record['matched'] = False
                if record not in calls:
                    calls.append(record)
                result = {'content': [{'type': 'text', 'text': '实验工具未完成'}], 'isError': True}
        elif 'id' not in value:
            self.send_response(202)
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        else:
            result = {}
        body = json.dumps({'jsonrpc': '2.0', 'id': value.get('id'), 'result': result}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
server.daemon_threads = True
thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
thread.start()
url = 'http://127.0.0.1:' + str(server.server_port) + '/mcp'
name = 'credential_contract'
planner = config['plannerConfig']
planner['customizationConfig'] = {'mcpServers': [{'serverName': name, 'serverUrl': url,
    'skipToolNamePrefix': True, 'skipToolDescriptionPrefix': True, 'forceAllToolsEager': True,
    'disableStandaloneSse': True}], 'skipToolNamePrefix': True, 'skipToolDescriptionPrefix': True}
planner['declarativeMixinConfig']['providers'] = [{'name': name, 'url': url, 'protocol': 'PROTOCOL_MCP'}]
planner['declarativeMixinConfig']['tools'] = [{'name': 'contract_read', 'providerName': name}]
planner['declarativeMixinConfig']['promptSections'] = [{'custom': {'content': '这是受控凭据实验。必须通过 contract_read 工具取得结果。'}}]
planner['toolConfig']['descriptionOverrideMap'] = {'toolOverrides': {'contract_read': {
    'argumentValueOverrides': {'toolSummary': {'omit': True}}}}}
status, initial = rpc('StartCascade', {'source': 'CORTEX_TRAJECTORY_SOURCE_AGENT_API', 'requestedModel': model})
summary['start_status'] = status
try:
    if status == 200 and initial.get('cascadeId'):
        cascade = initial['cascadeId']
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(rpc, 'SendUserCascadeMessage', {'cascadeId': cascade,
                'items': [{'text': '调用 contract_read，参数 key 为 sample。工具完成后只回复工具返回的唯一标记。'}],
                'additionalSteps': [], 'cascadeConfig': config, 'blocking': True, 'propagateError': True})
            deadline = time.monotonic() + 70
            while not called.wait(.1) and not future.done() and time.monotonic() < deadline:
                pass
            if called.is_set():
                path = Path('/home/agy/.gemini/antigravity-cli/antigravity-oauth-token')
                before = json.loads(path.read_text())
                after = json.loads(Path('/workspace/next-token.json').read_text())
                summary['different_access_token'] = not hmac.compare_digest(before['token']['access_token'], after['token']['access_token'])
                temporary = path.with_suffix('.publishing')
                temporary.write_text(json.dumps(after))
                temporary.chmod(0o600)
                temporary.replace(path)
                active = Path('/workspace/active.json')
                temporary = active.with_suffix('.publishing')
                temporary.write_text(json.dumps({'request_id': 'credential-tool-resumed'}))
                temporary.replace(active)
                summary['file_published_generation_2'] = True
                release.set()
            elif not future.done():
                rpc('CancelCascadeInvocation', {'cascadeId': cascade, 'killBackgroundTasks': True, 'notifyParent': False})
                release.set()
            status, result = future.result(timeout=110)
            Path('/workspace/tool-send-result.json').write_text(json.dumps(result))
            summary['send_status'] = status
        status, result = rpc('GetCascadeTrajectory', {'cascadeId': cascade})
        Path('/workspace/tool-trajectory.json').write_text(json.dumps(result))
        steps = result.get('trajectory', {}).get('steps', [])
        planners = [step for step in steps if 'plannerResponse' in step]
        summary.update(trajectory_status=status, step_types=[step.get('type') for step in steps],
            observed_planner_steps=len(planners), marker_observed=any(
                step['plannerResponse'].get('response', '').strip() == 'AGY_REAL_TOOL_RESULT_OK' for step in planners),
            tool_calls=calls, tool_effect_count=len(Path('/workspace/tool-effects.txt').read_text().splitlines())
                if Path('/workspace/tool-effects.txt').exists() else 0)
finally:
    release.set()
    server.shutdown()
    server.server_close()
    thread.join(2)
print(json.dumps(summary))
