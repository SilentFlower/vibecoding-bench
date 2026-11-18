"""通过已定义的原生 RPC 验证一次 AT-only 模型生成。"""
MODEL_REQUEST_LIMIT = 1
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
status, value = rpc('StartCascade', {'source': 'CORTEX_TRAJECTORY_SOURCE_AGENT_API', 'requestedModel': model})
summary = {'evidence': 'native_oauth', 'scope': 'at_only_text_observed', 'start_status': status,
    'requested_model': model, 'reserved_generations': 1}
if status == 200 and value.get('cascadeId'):
    cascade = value['cascadeId']
    status, result = rpc('SendUserCascadeMessage', {'cascadeId': cascade,
        'items': [{'text': '仅回复 AGY_AT_ONLY_CONTRACT_OK'}], 'additionalSteps': [],
        'cascadeConfig': config, 'blocking': True, 'propagateError': True})
    Path('/workspace/native-send-result.json').write_text(json.dumps(result))
    summary['send_status'] = status
    status, result = rpc('GetCascadeTrajectory', {'cascadeId': cascade})
    Path('/workspace/native-trajectory.json').write_text(json.dumps(result))
    steps = result.get('trajectory', {}).get('steps', [])
    planners = [step for step in steps if 'plannerResponse' in step]
    summary.update(trajectory_status=status, step_types=[step.get('type') for step in steps],
        planner_statuses=[step.get('status') for step in planners],
        observed_planner_steps=len(planners), marker_observed=any(step['plannerResponse'].get('response', '').strip() == 'AGY_AT_ONLY_CONTRACT_OK' for step in planners),
        generator_models=[step.get('metadata', {}).get('generatorModel') for step in planners])
print(json.dumps(summary))
