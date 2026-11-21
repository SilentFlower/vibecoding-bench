"""在一次性断网回环内制造两个与主根并发的真实 AGY 调用。"""
import base64
import copy
import json
from pathlib import Path


def install(kernel, bridge, rpc):
    """给回环专用内核装入故障夹具。

    @param kernel 私有内核类型。
    @param bridge 私有帧读取器类型。
    @param rpc 实际本地原生 RPC 类型。
    @return 无。
    """
    original_publish = kernel.publish_tool_wait
    original_emit = bridge._emit

    def publish(self, scope):
        """在主工具批次发布前运行两笔受控的独立级联。@param scope 主请求。@return 原发布结果。"""
        body = scope.value.get('gemini_body') or {}
        contents = body.get('contents') or []
        results = sum('functionResponse' in part for turn in contents for part in turn.get('parts', []))
        if results == 1 and 'AGY_RECEIPT_OWNERSHIP' in json.dumps(contents):
            scope.fixture_aux_roots = {}
            cfg = copy.deepcopy(self.base_config)
            model = scope.value['model']
            cfg['plannerConfig']['planModel'] = model
            cfg['plannerConfig']['retryConfig']['modelOutputRetry'] = {'maxRetries':0}
            cfg['executorConfig']['maxGeneratorInvocations'] = 1
            calls = []
            for index in range(2):
                result = scope.worker.call('StartCascade', {
                    'source':'CORTEX_TRAJECTORY_SOURCE_AGENT_API','requestedModel':model}, scope)
                if result['status'] != 200:
                    raise RuntimeError('合成独立级联启动失败')
                root = result['response']['cascadeId']
                scope.fixture_aux_roots[root] = index
                calls.append(rpc(scope.worker, 'SendUserCascadeMessage', {
                    'cascadeId':root,'items':[{'text':f'AGY_RECEIPT_SIDE_{index}'}],'additionalSteps':[],
                    'cascadeConfig':cfg,'blocking':True,'propagateError':True}, scope))
            for call in calls:
                if not call.done.wait(12) or not call.value or call.value['status'] != 200:
                    raise RuntimeError('合成独立级联控制失败')
        return original_publish(self, scope)

    def emit(self, event):
        """记录实际调用与原始帧，并重放一次空会话身份。

        @param event 观察器发出的实际事件。
        @return 原读取器交付结果。
        """
        scope = self.worker.owner.active
        roots = getattr(scope, 'fixture_aux_roots', {})
        if roots:
            kind = event['event']
            row = {'event':kind,'call_id':event.get('call_id')}
            if kind == 'model_start':
                context = event['native_context']
                index = roots.get(context.get('ConversationID'))
                row['side'] = index
                if index == 0:
                    # 线上观察过空会话 ID。保留真实的 Go 调用与帧身份，只重放缺省上下文。
                    event = {**event,'native_context':{**context,'ConversationID':''}}
            elif kind == 'gemini_response':
                data = base64.b64decode(event['data_base64'])
                row['side'] = next((index for index in range(2)
                    if f'AGY_RECEIPT_SIDE_{index}'.encode() in data), None)
                row['raw_epoch'] = event['raw_epoch']
            if kind in ('model_start','model_end','gemini_response','observer_error'):
                with Path('/state/fixture-tool-owners.ndjson').open('a') as output:
                    output.write(json.dumps(row)+'\n')
        return original_emit(self, event)

    kernel.publish_tool_wait = publish
    bridge._emit = emit
