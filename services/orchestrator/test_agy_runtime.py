"""使用合成凭据及真实文件核对AGY原生运行边界，模型提交为零。"""
import base64
import copy
import gzip
import json
import io
import os
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener
from unittest.mock import patch
from types import SimpleNamespace

from agy_runtime import gemini_contract
from agy_runtime.contract import InputError, request
from agy_runtime.credentials import TOKEN_PATH, publish_access_document, read_access_document, read_private
from agy_runtime.criu import read_failure
from agy_runtime.gemini_frames import Frames
from agy_runtime.models import decode_catalog, decode_media_support, decode_png_support
from agy_runtime.native_bridge import NativeBridge
from agy_runtime.process_memory import cgroup_memory
from agy_runtime.safety_egress import MODEL_PATH, SafetyEgress, _Request
from agy_runtime.kernel import Bridge, Kernel, Scope, Worker
from agy_runtime.stream_controller import NativeJob
from agy_runtime.supervisor import Supervisor
from agy_runtime.tool_broker import Broker
from agy_runtime.tool_schema import normalize
from agy_runtime.storage import Output, config
from runtime_files import atomic_json


class AgyRuntimeTests(unittest.TestCase):
    """验证协议语义、账号凭据及原生启动环境。"""

    def setUp(self):
        """建立独立私有文件根及固定模型。@return 无。"""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.fixed_model = ('gemini-synthetic', 'MODEL_PLACEHOLDER_M36')

    def snapshot(self):
        """创建同代AT-only管理快照。@return 合成快照。"""
        return {'account_id': 17, 'credential_generation': 4, 'access_token': 'synthetic-at',
            'expires_at': int((datetime.now(timezone.utc) + timedelta(hours=2)).timestamp() * 1000),
            'email': 'synthetic@example.test'}

    def test_isolated_calls_do_not_change_completed_tool_stream(self):
        """主轮 EOF 后隔离交错的独立调用，同会话的第二次启动仍计入原作业。@return 无。"""
        cases = [('STOP', 'other', 'foreign_model_observed'), ('STOP', '', 'unassigned_model_observed'),
            ('MAX_TOKENS', 'other', 'foreign_model_observed')]
        for finish_reason, conversation, isolation in cases:
            with self.subTest(finish_reason=finish_reason, conversation=conversation):
                bridge=Bridge.__new__(Bridge)
                worker=Worker.__new__(Worker)
                recorded=[]
                worker.owner=SimpleNamespace(emit=lambda kind, **fields: recorded.append(kind))
                scope=SimpleNamespace(worker=worker,route='r-1',root='owned',isolated_call_ids=set(),
                    broker=SimpleNamespace(gemini_results=None),tool_wait_published=False,
                    value={'request_format':'gemini'},frames=Frames(),identity=lambda: {},tls_trace=None,safety_egress=None)
                worker.owner.active=scope
                bridge.worker=worker
                bridge.events=io.StringIO();bridge.errors=[];bridge.source_events=0
                bridge.active_job=scope.job=NativeJob(scope.route,SimpleNamespace(offer=lambda event: True))
                owned={'event':'model_start','request_id':scope.route,'call_id':'r-1.1','ns':1,
                    'native_context':{'ConversationID':'owned'}}
                extra={**owned,'call_id':'r-1.2','native_context':{'ConversationID':conversation}}
                bridge._emit(owned)
                with self.assertRaisesRegex(RuntimeError,'native_root_identity.unfinished_stream'):
                    bridge._emit(extra)
                call={'name':'fixture','args':{'x':1}}
                frame=json.dumps({'candidates':[{'content':{'parts':[{'functionCall':call}]},'finishReason':finish_reason}]}).encode()
                bridge._emit({**owned,'event':'gemini_response','data_base64':base64.b64encode(frame).decode()})
                with self.assertRaisesRegex(RuntimeError,'source_call_identity'):
                    bridge._emit({**extra,'event':'model_end','native_error_present':None})
                bridge._emit({**owned,'event':'model_end','native_error_present':None})
                another={**extra,'call_id':'r-1.3'}
                bridge._emit(extra)
                bridge._emit(another)
                bridge._emit({**extra,'event':'gemini_response','data_base64':'外部帧禁止解析'})
                bridge._emit({**another,'event':'gemini_response','data_base64':'外部帧禁止解析'})
                bridge._emit({**extra,'event':'model_end','native_error_present':None})
                bridge._emit({**another,'event':'model_end','native_error_present':None})
                self.assertEqual(recorded,['model_start','gemini_response','model_end',isolation,isolation])
                self.assertEqual((scope.job.calls,scope.job.ends),(1,1))
                self.assertEqual(scope.frames.calls[0]['name'],call['name'])
                self.assertTrue(scope.frames.calls[0]['id'].startswith('call_'))
                self.assertTrue(scope.job.ended.is_set())
                with self.assertRaisesRegex(RuntimeError,'native_root_identity.call_reused'):
                    bridge._emit({**owned,'call_id':extra['call_id']})
                with self.assertRaisesRegex(RuntimeError,'source_call_identity'):
                    bridge._emit({**another,'event':'gemini_response','call_id':'r-1.unknown'})
                bridge._emit({**owned,'call_id':'r-1.4'})
                self.assertEqual(scope.job.calls,2)

    def test_model_result_survives_only_post_stream_control_failure(self):
        """通过真实执行入口区分已结束的结果、断流、工具和取消。@return 无。"""
        usage={'promptTokenCount':12,'candidatesTokenCount':2,'totalTokenCount':14}
        text = [{'text': '合成模型结果'}]
        thinking = [{'text': '合成思考', 'thought': True}]
        media = [{'inlineData': {'mimeType': 'image/png', 'data': 'aW1hZ2U='}}]
        thinking_usage = {'promptTokenCount': 12, 'totalTokenCount': 42, 'thoughtsTokenCount': 30}
        max_tokens_cases = {
            'max_tokens_rpc_200': (text, usage, 'kept'),
            'max_tokens_text': (text, usage, 'kept'),
            'max_tokens_thinking': (thinking, {**thinking_usage, 'candidatesTokenCount': 0}, 'kept'),
            'max_tokens_without_candidates': (thinking, thinking_usage, 'kept'),
            'max_tokens_media': (media, usage, 'kept'),
            'max_tokens_missing_output': ([], usage, 'missing_text'),
            'max_tokens_invalid_candidates': (thinking, {**thinking_usage, 'candidatesTokenCount': None}, 'missing_usage'),
            'max_tokens_invalid_thoughts': (thinking, {**thinking_usage, 'thoughtsTokenCount': True}, 'missing_usage'),
        }
        cases=[('rpc_503','completed'),('rpc_400','error'),('not_idle','completed'),('late_observer_error','completed'),
            ('missing_stop','error'),('missing_usage','error'),('pending_tool','error'),('unregistered_tool','error'),
            ('early_observer_error','error'),('second_model_call','error'),('cancelled','cancelled'),
            ('late_eof_clean','error'),('late_eof_truncated','error')]
        cases.extend((mode, 'completed' if reason == 'kept' else 'error')
            for mode, (_, _, reason) in max_tokens_cases.items())
        for mode,expected in cases:
            with self.subTest(mode=mode):
                max_tokens_case = max_tokens_cases.get(mode)
                kernel=Kernel.__new__(Kernel)
                kernel.state=self.root/mode;kernel.state.mkdir()
                kernel.cfg={'capture_enabled':False,'rotate_after':None}
                kernel.base_config={'plannerConfig':{'declarativeMixinConfig':{},'retryConfig':{}},
                    'executorConfig':{},'trajectoryConversionConfig':{}}
                kernel.lock=threading.Lock();kernel.closing=False
                events=[];retirements=[];submissions=[]
                kernel.emit=lambda kind,**fields:events.append((kind,fields))
                worker=Worker.__new__(Worker);worker.owner=kernel;worker.jobs=0;worker.ready=True
                worker.retire=lambda reason:retirements.append(reason)
                def control(method, body, scope):
                    """投影真实控制入口的合成结果。@param method 控制方法。@param body 输入。@param scope 作业。@return 控制回应。"""
                    if method=='StartCascade':
                        self.assertEqual(body['requestedModel'], self.fixed_model[1])
                        return {'status':200,'response':{'cascadeId':'owned'}}
                    self.assertEqual(method,'GetCascadeTrajectory')
                    state='CASCADE_RUN_STATUS_RUNNING' if mode=='not_idle' else 'CASCADE_RUN_STATUS_IDLE'
                    return {'status':200,'response':{'status':state,'trajectory':{'trajectoryId':'fixture','steps':[]}}}
                worker.call=control
                bridge=Bridge.__new__(Bridge);bridge.worker=worker;bridge.run_folder=kernel.state
                bridge.events=io.StringIO();bridge.errors=[];bridge.source_events=0;bridge.reader_error=None
                bridge.proc=SimpleNamespace(poll=lambda:None)
                bridge.generation='synthetic-generation';bridge.capture_tls=False;worker.bridge=bridge
                value={'request_id':'synthetic','request_format':'gemini','native_steps':[],
                    'prompt':'fixture','system':'','model':self.fixed_model[1],'max_generations':1,'tools':[]}
                if max_tokens_case:
                    value['native_completion'] = {'maxTokens': 30}
                scope=Scope(value,1,worker);kernel.worker=worker;kernel.active=scope

                def submit(worker, method, body, scope):
                    """交付原始帧后注入控制异常。@param worker 进程。@param method 方法。@param body 提交。@param scope 作业。@return 异步结果。"""
                    self.assertEqual(method,'SendUserCascadeMessage');submissions.append(body['cascadeId'])
                    self.assertEqual(body['cascadeConfig']['plannerConfig']['planModel'], self.fixed_model[1])
                    event={'request_id':scope.route,'call_id':'r-1.1','ns':1,
                        'native_context':{'ConversationID':'owned'}}
                    bridge._emit({**event,'event':'model_start'})
                    candidate={'content':{'parts':[{'text':'合成模型结果'}]}}
                    if mode not in ('missing_stop','rpc_400'):candidate['finishReason']='STOP'
                    if mode in ('pending_tool','unregistered_tool'):
                        candidate['content']['parts'].append({'functionCall':{'name':'fixture'}})
                    frame={'candidates':[candidate]}
                    if mode.startswith('late_eof_'):frame={}
                    if mode!='missing_usage':frame['usageMetadata']=usage
                    if max_tokens_case:
                        self.assertEqual(body['cascadeConfig']['plannerConfig']['completionConfigOverride']['maxTokens'], 30)
                        candidate.update(finishReason='MAX_TOKENS', content={'parts': max_tokens_case[0]})
                        frame['usageMetadata'] = max_tokens_case[1]
                    encoded=base64.b64encode(json.dumps(frame).encode()).decode()
                    bridge._emit({**event,'event':'gemini_response','data_base64':encoded})
                    if mode=='early_observer_error':bridge._emit({'event':'observer_error','ns':2})
                    bridge._emit({**event,'event':'model_end','ns':3,'native_error_present':None})
                    if mode=='late_observer_error':bridge._emit({'event':'observer_error','ns':4,'error':'SDK原始帧缺少模型调用'})
                    if mode=='second_model_call':bridge._emit({**event,'event':'model_start','call_id':'r-1.2'})
                    if mode=='cancelled':scope.cancel.set()
                    done=threading.Event();done.set()
                    status={'not_idle':200,'late_observer_error':200,'unregistered_tool':200,'rpc_400':400,
                        'late_eof_clean':200,'late_eof_truncated':500}.get(mode,503)
                    if max_tokens_case:
                        status = 200 if mode == 'max_tokens_rpc_200' else 500
                    if mode.startswith('late_eof_'):
                        pending=SimpleNamespace(error=None,value=None,response_status=None)
                        def wait(_timeout):
                            """先交付接收通道关闭，再暴露下一拍到达的控制响应。@param _timeout 等待时间。@return 控制响应是否已到。"""
                            if done.is_set():
                                done.clear()
                                return False
                            pending.response_status=status
                            pending.value={'status':status,'response':{'message':'stream reading error: unexpected EOF'} if status==500 else {}}
                            return True
                        pending.done=SimpleNamespace(wait=wait)
                        return pending
                    return SimpleNamespace(done=done,error=None,value={'status':status},response_status=status)

                with patch('agy_runtime.kernel.RPC',side_effect=submit):kernel.execute(scope)
                terminal=[(kind,fields) for kind,fields in events if kind in ('completed','error','cancelled')]
                self.assertEqual([kind for kind,_ in terminal],[expected],terminal)
                self.assertEqual(submissions,['owned'])
                if mode == 'max_tokens_rpc_200':
                    self.assertEqual(terminal[0][1]['finish_reason'], 'max_tokens')
                    self.assertEqual(retirements, [])
                    self.assertEqual(events[-1][0], 'idle')
                    self.assertEqual(events[-1][1]['next_generation'], bridge.generation)
                    continue
                self.assertEqual(retirements,['request_error'])
                self.assertEqual(events[-1][0],'idle')
                self.assertIsNone(events[-1][1]['next_generation'])
                diagnostic=[kind for kind,_ in events if kind.startswith('native_control.')]
                reasons={'rpc_503':'kept','rpc_400':'missing_stop','not_idle':'kept','late_observer_error':'kept',
                    'missing_stop':'missing_stop','missing_usage':'missing_usage','pending_tool':'tool_pending',
                    'unregistered_tool':'ineligible_error',
                    'early_observer_error':'observer_before_eof','second_model_call':'model_call_count','cancelled':'ineligible_error',
                    'late_eof_clean':'ineligible_error','late_eof_truncated':'missing_stop'}
                if max_tokens_case:
                    reasons[mode] = max_tokens_case[2]
                    fields = terminal[0][1]
                    self.assertEqual(fields['observed_control_http_status'], 500)
                    self.assertTrue(fields['native_receive_ended'])
                    self.assertTrue(fields['native_source_terminal'])
                    if expected == 'completed':
                        self.assertEqual(fields['finish_reason'], 'max_tokens')
                        delivered = [json.loads(base64.b64decode(event['data']['data_base64']))
                            for kind, event in events if kind == 'gemini_response']
                        self.assertEqual(len(delivered), 1)
                        self.assertEqual(delivered[0]['usageMetadata'], max_tokens_case[1])
                        self.assertEqual(delivered[0]['candidates'][0]['finishReason'], 'MAX_TOKENS')
                        self.assertEqual(delivered[0]['candidates'][0]['content']['parts'], max_tokens_case[0])
                    else:
                        self.assertEqual(fields['control_http_status'], 500)
                self.assertEqual(len(diagnostic),1)
                self.assertEqual(diagnostic[0].rsplit('.',1)[-1],reasons[mode])
                self.assertEqual(terminal[0][1]['control_recovery'],reasons[mode])
                if mode=='rpc_503':
                    self.assertEqual(diagnostic[0],'native_control.submission.native_request_failed.503.RuntimeError.kept')
                if mode=='rpc_400':
                    self.assertEqual(terminal[0][1]['control_http_status'],400)
                    self.assertEqual(terminal[0][1]['code'],'native_request_failed')
                if mode=='late_observer_error':
                    self.assertIn('native_protocol.observer.sdk_call_missing',[kind for kind,_ in events])
                if mode=='unregistered_tool':
                    self.assertEqual(terminal[0][1]['code'],'tool_protocol_error')
                    self.assertNotIn('control_http_status',terminal[0][1])
                if mode.startswith('late_eof_'):
                    fields=terminal[0][1]
                    self.assertTrue(fields['native_receive_ended'])
                    self.assertFalse(fields['native_source_terminal'])
                    if mode=='late_eof_clean':
                        self.assertEqual(fields['observed_control_http_status'],200)
                        self.assertEqual(fields['code'],'native_stream_incomplete')
                    else:
                        self.assertEqual(fields['control_http_status'],500)
                        self.assertEqual(fields['control_error_detail'],'unexpected_eof')
                if expected=='completed':
                    expected_code={'not_idle':'native_not_idle',
                        'late_observer_error':'native_protocol_error'}.get(mode, 'native_request_failed')
                    self.assertEqual(terminal[0][1]['control_error_code'],expected_code)
                    self.assertFalse(terminal[0][1]['native_tool_pending'])
                    self.assertNotIn('control_http_status',terminal[0][1])

    def test_control_rpc_retains_http_error_with_non_json_body(self):
        """保留实际错误状态，成功或缺失状态时仍按传输失败处理。@return 无。"""
        worker = Worker.__new__(Worker)
        done = threading.Event()
        done.set()
        future = SimpleNamespace(done=done, error='JSONDecodeError', response_status=502)
        with patch('agy_runtime.kernel.RPC', return_value=future):
            self.assertEqual(worker.call('StartCascade', {}, None), {'status': 502, 'response': None})
            for status in (200, None):
                with self.subTest(status=status):
                    future.response_status = status
                    with self.assertRaisesRegex(RuntimeError, 'native_transport_error'):
                        worker.call('StartCascade', {}, None)

    def test_gemini_text_modality_uses_native_default(self):
        """确认显式文本输出沿用默认行为，图片和音频仍保留字段级错误。@return 无。"""
        raw = {'schema_version': 1, 'type': 'gemini_request', 'request_id': 'modalities',
               'model': 'gemini-synthetic', 'body': {'contents': [{'parts': [{'text': '合成请求'}]}]}}
        expected = gemini_contract.decode_request(raw, fixed_model=self.fixed_model)['native_completion']
        for modalities in ([], ['TEXT']):
            raw['body']['generationConfig'] = {'responseModalities': modalities}
            self.assertEqual(gemini_contract.decode_request(raw, fixed_model=self.fixed_model)['native_completion'], expected)
        for modalities in (None, 'TEXT', ['IMAGE'], ['TEXT', 'AUDIO']):
            raw['body']['generationConfig'] = {'responseModalities': modalities}
            with self.subTest(modalities=modalities), self.assertRaisesRegex(
                    InputError, 'unsupported_gemini_output_modality:/body/generationConfig/responseModalities'):
                gemini_contract.decode_request(raw, fixed_model=self.fixed_model)

    def test_gemini_normalizes_nested_array_items_and_string_const(self):
        """从 Gemini 两类工具声明保留已知类型，并记录真实缺项与常量改写位置。@return 无。"""
        schema = {'type': 'OBJECT', 'properties': {'query': {'type': 'OBJECT', 'properties': {
            'where': {'type': 'ARRAY', 'items': {'type': 'ARRAY'}},
            'tags': {'type': 'ARRAY', 'items': {'type': 'STRING'}},
            'action': {'const': 'query', 'enum': ['query', 'list']},
            'revision': {'type': 'INTEGER', 'const': 7},
        }}}}
        raw = {'schema_version': 1, 'type': 'gemini_request', 'request_id': 'tool-schema',
            'model': 'gemini-synthetic', 'body': {'contents': [{'parts': [{'text': '合成请求'}]}],
                'tools': [{'functionDeclarations': [{'name': 'tool_' + key, key: schema}
                    for key in ('parameters', 'parametersJsonSchema')]}]}}
        original = copy.deepcopy(raw)
        decoded = gemini_contract.decode_request(raw, fixed_model=self.fixed_model)
        for tool in decoded['tools']:
            query = tool['input_schema']['properties']['query']['properties']
            self.assertEqual(query['where']['items']['items'], {'anyOf': [{}]})
            self.assertEqual(query['tags']['items'], {'type': 'string'})
            self.assertEqual(query['action'], {'type': 'string', 'enum': ['query']})
            self.assertEqual(query['revision'], {'type': 'integer', 'const': 7})
            changes = []
            self.assertEqual(normalize(tool['input_schema'], changes=changes), tool['input_schema'])
            self.assertEqual(changes, [])
        self.assertEqual(raw, original)
        for action, suffix in (('array_items_as_schema', '/properties/query/properties/where/items/items'),
                ('string_const_as_enum', '/properties/query/properties/action/const')):
            self.assertEqual(sum(item['action'] == action and item['path'].endswith(suffix)
                for item in decoded['schema_changes']), 2)

    def test_schema_preserves_tuple_types_and_closed_length(self):
        """新版和旧版闭合元组保留候选类型与长度，显式允许的尾部仍可传递。@return 无。"""
        elements = [{'type': 'string'}, {'const': 'eq'}, {'type': 'number'}, {'type': 'boolean'}]
        expected = {'type': 'array', 'minItems': 2, 'maxItems': 4, 'items': {'anyOf': [
            {'type': 'string'}, {'type': 'string', 'enum': ['eq']}, {'type': 'number'}, {'type': 'boolean'}]}}
        for tuple_schema in ({'prefixItems': elements, 'items': False},
                {'items': elements, 'additionalItems': False}):
            changes = []
            actual = normalize({'type': 'array', 'minItems': 2, 'maxItems': 9, **tuple_schema},
                '/where/items', changes)
            self.assertEqual(actual, expected)
            self.assertTrue(any(item['action'] == 'tuple_as_array_items' for item in changes))
            self.assertEqual(normalize(actual), actual)
        self.assertEqual(normalize({'type': 'ARRAY', 'prefixItems': [{'type': 'STRING'}],
            'items': {'type': 'BOOLEAN'}})['items'], {'anyOf': [{'type': 'string'}, {'type': 'boolean'}]})
        self.assertEqual(normalize({'type': 'array', 'prefixItems': elements, 'maxItems': 1})['items'], {'type': 'string'})
        self.assertEqual(normalize({'type': 'array', 'prefixItems': elements, 'items': False, 'maxItems': '1'}),
            {'type': 'array', 'maxItems': 1, 'items': {'type': 'string'}})
        self.assertEqual(normalize({'type': 'array', 'prefixItems': elements})['items'], {'anyOf': [{}]})
        self.assertEqual(normalize({'type': 'array', 'items': False}),
            {'type': 'array', 'maxItems': 0, 'items': {'anyOf': [{}]}})

    def test_schema_rejects_conflicting_string_const_and_enum(self):
        """不扩大互相矛盾的约束，并保留实际拒绝路径。@return 无。"""
        with self.assertRaisesRegex(InputError, 'invalid_tool_schema:/action/const'):
            normalize({'const': 'query', 'enum': ['list']}, '/action')

    def test_safety_egress_validates_binding_and_sends_model_once(self):
        """覆盖口令、随机路径、压缩正文和重复模型提交。@return 无。"""
        rules=[{'category':'HARM_CATEGORY_HARASSMENT','threshold':'BLOCK_MEDIUM_AND_ABOVE'}]
        token='synthetic-access'
        outbound=[]
        def forward(handler, scope, path, headers, raw):
            outbound.append((path, headers, json.loads(gzip.decompress(raw))))
            handler.send_response(200)
            handler.end_headers()
        egress=SafetyEgress(rules,token,'http://127.0.0.1:1080')
        self.addCleanup(egress.close)
        opener=build_opener(ProxyHandler({}))
        body={'request':{'contents':[{'parts':[{'text':'合成请求'}]}]}}
        def post(url, bearer):
            compressed=gzip.compress(json.dumps(body).encode())
            request=Request(url,data=iter([compressed[:5],compressed[5:]]),
                headers={'Authorization':'Bearer '+bearer,'Content-Encoding':'gzip'})
            return opener.open(request,timeout=2)
        with patch.object(_Request,'_forward',forward):
            for target,bearer in ((egress.url+MODEL_PATH,'invalid'),(egress.url+'/wrong'+MODEL_PATH,token)):
                with self.assertRaises(HTTPError) as exc:
                    post(target,bearer)
                self.assertIn(exc.exception.code,(403,404))
            with post(egress.url+MODEL_PATH,token) as response:
                self.assertEqual(response.status,200)
            with self.assertRaises(HTTPError) as exc:
                post(egress.url+MODEL_PATH,token)
            self.assertEqual(exc.exception.code,409)
        self.assertEqual(len(outbound),1)
        self.assertIn('Content-Encoding: gzip',outbound[0][1])
        self.assertIn('Transfer-Encoding: chunked',outbound[0][1])
        self.assertEqual(outbound[0][2]['request'],{**body['request'],'safetySettings':rules})

    def test_cgroup_versions_keep_ram_swap_and_unknown_limits_distinct(self):
        """真实文件覆盖v1/v2预算、无限哨兵、损坏及未知，防止合法环境被拒绝。@return 无。"""
        for version,relative in [('cgroup_v2','v2'),('cgroup_v1','v1/memory'),('cgroup_v1','flat')]:
            directory=self.root/relative
            directory.mkdir(parents=True)
            files={'memory.max':'805306368','memory.current':'100','memory.peak':'120','memory.swap.current':'7'} if version=='cgroup_v2' else {
                'memory.limit_in_bytes':'805306368','memory.usage_in_bytes':'100','memory.max_usage_in_bytes':'120','memory.memsw.usage_in_bytes':'107'}
            for name,value in files.items():(directory/name).write_text(value)
            root=directory.parent if relative=='v1/memory' else directory
            self.assertEqual(cgroup_memory(root),{'source':version,'max_bytes':805306368,'current_bytes':100,'peak_bytes':120,'swap_bytes':7})
            limit=directory/('memory.max' if version=='cgroup_v2' else 'memory.limit_in_bytes')
            limit.write_text('max' if version=='cgroup_v2' else '9223372036854771712')
            self.assertEqual(cgroup_memory(root)['max_bytes'],'unlimited')
            for invalid in ['0','-1','损坏']:
                limit.write_text(invalid)
                self.assertIsNone(cgroup_memory(root)['max_bytes'])
            limit.unlink()
            self.assertIsNone(cgroup_memory(root)['max_bytes'])
        self.assertEqual(cgroup_memory(self.root/'missing')['source'],'unknown')

    def test_supervisor_rejects_unknown_or_mismatched_memory_before_launch(self):
        """未知限制不能冒充无限，失败必须发生在启动映像池之前。@return 无。"""
        for budget,actual in [(0,None),(768,None),(768,1024),(0,805306368)]:
            with patch('agy_runtime.supervisor.cgroup_memory',return_value={'max_bytes':actual}), patch('agy_runtime.supervisor.ImagePool') as pool:
                with self.assertRaisesRegex(ValueError,'冻结RAM预算'):
                    Supervisor({'memory_mib':budget})
                pool.assert_not_called()

    def test_supervisor_reserves_and_reuses_one_prepared_replacement(self):
        """同身份续轮等待已有的预热，失败或过时代次归还物理名额。@return 无。"""
        for mode in ('ready','failure','stale','capacity'):
            with self.subTest(mode=mode):
                value={'credential_snapshot':self.snapshot(),'model':'gemini-synthetic',
                    'native_model':'MODEL_PLACEHOLDER_M36','capture_enabled':False}
                supervisor=Supervisor.__new__(Supervisor)
                supervisor.condition=threading.Condition();supervisor.closed=False
                supervisor.search_slots=0
                supervisor.restore_enabled=False
                supervisor.config={'max_workers':1 if mode=='capacity' else 3,'proxy_url':'synthetic'}
                supervisor.credential_generation=value['credential_snapshot']['credential_generation']
                key=supervisor.worker_key(value)
                original=SimpleNamespace(key=key,busy=True,closed=False,prewarming=False,parked=False)
                supervisor.workers=[original]
                spare=SimpleNamespace(key=key,busy=True,closed=False,parked=False,start_source='exec',
                    credential_expires_at=value['credential_snapshot']['expires_at'],process=None)
                entered=threading.Event();release=threading.Event();checked_out=[]
                until=time.monotonic()+5

                def start(_until):
                    """控制准备握手的观察顺序。@param _until 截止。@return 无。"""
                    if mode=='failure':raise InputError('worker_start_failed')
                    if mode=='stale':supervisor.credential_generation+=1
                    if mode=='ready':
                        entered.set();release.wait(3)
                        spare.process=SimpleNamespace(poll=lambda: None)

                spare.start=start
                spare.close=lambda: setattr(spare,'closed',True)
                spare.running=lambda: spare.process is not None and not spare.closed
                with patch('agy_runtime.supervisor.Worker',return_value=spare) as factory:
                    if mode=='ready':
                        warming=threading.Thread(target=supervisor.prewarm_replacement,args=(original,value,until),daemon=True)
                        warming.start()
                        try:
                            self.assertTrue(entered.wait(2))
                            self.assertEqual(supervisor.workers,[original,spare])
                            self.assertTrue(spare.prewarming)
                            checkout=threading.Thread(target=lambda: checked_out.append(supervisor.acquire(value,until)),daemon=True)
                            checkout.start()
                        finally:
                            release.set();warming.join(3)
                        checkout.join(3)
                        self.assertEqual(checked_out,[spare])
                        self.assertFalse(spare.prewarming)
                        self.assertTrue(original.busy)
                        factory.assert_called_once()
                    else:
                        supervisor.prewarm_replacement(original,value,until)
                        self.assertEqual(supervisor.workers,[original])
                        if mode=='capacity':factory.assert_not_called()
                        else:self.assertTrue(spare.closed)

    def test_template_failure_survives_fallback_and_stays_with_current_credentials(self):
        """同代模板失败后保留首个受控原因，普通回退仍取得原物理名额。@return 无。"""
        snapshot=self.snapshot()
        value={'type':'prepare','credential_snapshot':snapshot,'model':'gemini-synthetic',
            'native_model':'MODEL_PLACEHOLDER_M36'}
        supervisor=Supervisor.__new__(Supervisor)
        supervisor.condition=threading.Condition();supervisor.closed=False
        supervisor.search_slots=0
        supervisor.config={'max_workers':1,'proxy_url':'synthetic'}
        supervisor.credential_generation=snapshot['credential_generation']
        supervisor.workers=[];supervisor.template_failure=None
        supervisor.restore_available=lambda: True
        failure={'stage':'observer_start','reason':'execution_mapping_missing'}
        key=supervisor.worker_key(value)
        template=SimpleNamespace(key=key,credential_expires_at=snapshot['expires_at'],parked=False,
            criu_failure=read_failure(failure),close=lambda: None)
        normal=SimpleNamespace(key=key,parked=False,start=lambda until: None)

        def fail_start(until):
            """按原截止模拟首个模板错误。@param until 原请求截止。@return 无。"""
            raise InputError('worker_start_failed')

        template.start=fail_start
        with patch('agy_runtime.supervisor.Worker',side_effect=[template,normal]) as factory:
            self.assertIs(supervisor.acquire(value,time.monotonic()+5),normal)
            self.assertEqual(factory.call_count,2)
        self.assertEqual(supervisor.workers,[normal])
        self.assertEqual(supervisor.template_failure,failure)
        self.assertIsNone(read_failure({**failure,'reason':'synthetic-secret'}))
        with supervisor.condition:
            supervisor.record_template_attempt(template,True)
            supervisor.credential_generation+=1
            supervisor.record_template_attempt(template,False)
        self.assertIsNone(supervisor.template_failure)

    def test_reaper_keeps_busy_workers_and_extra_workers_before_idle_deadline(self):
        """回收超期额外进程，保留未过空闲期限的进程及活动工具轮。@return 无。"""
        supervisor = Supervisor.__new__(Supervisor)
        supervisor.condition = threading.Condition()
        supervisor.closed = False
        supervisor.search_slots = 0
        supervisor.credential_generation = 1
        supervisor.config = {'max_workers': 4}
        supervisor.restore_allowed = True
        released = threading.Event()
        now = time.monotonic()

        def worker(key, age, busy=False):
            """构造活进程或占用中的原工具进程。@param key 复用键。@param age 空闲时长。@param busy 是否独占。@return 测试进程。"""
            return SimpleNamespace(key=(1, key), last_used=now-age, busy=busy, parked=False,
                credential_expires_at=4070908800000, process=SimpleNamespace(poll=lambda: None),
                close=released.set, running=lambda: True)

        old, current, tool, other = worker('same', 121), worker('same', 1), worker('same', 300, True), worker('other', 3)
        supervisor.workers = [old, current, tool, other]
        thread = threading.Thread(target=supervisor.reap_idle, daemon=True)
        thread.start()
        try:
            self.assertTrue(released.wait(2))
            with supervisor.condition:
                self.assertTrue(supervisor.condition.wait_for(lambda: old not in supervisor.workers, timeout=2))
                self.assertEqual(supervisor.workers, [current, tool, other])
        finally:
            with supervisor.condition:
                supervisor.closed = True
                supervisor.condition.notify_all()
            thread.join(2)

    def test_kernel_completion_reaches_real_tool_broker_once(self):
        """原生 ID 重复时按原步骤各完成一次反序混合回填。@return 无。"""
        body={'contents':[{'role':'user','parts':[{'text':'合成问题'}]}]}
        call={'id':'synthetic-call','name':'synthetic_tool','args':{'x':1}}
        frames=Frames()
        parts=[{'functionCall':call,'thoughtSignature':'synthetic-signature'},
            {'functionCall':{'id':'synthetic-call','name':'synthetic_tool','args':{'x':2}}}]
        source={'candidates':[{'content':{'parts':parts},'finishReason':'STOP'}]}
        projected=frames.project({'data_base64':base64.b64encode(json.dumps(source).encode()).decode()})
        public_parts=[json.loads(base64.b64decode(frame['data_base64']))['candidates'][0]['content']['parts'][0]
            for frame in projected]
        self.assertEqual(public_parts[0],parts[0])
        self.assertTrue(public_parts[1]['functionCall']['id'].startswith('call_'))
        self.assertEqual(frames.source_call_ids,['synthetic-call','synthetic-call'])
        incoming=copy.deepcopy(body)
        incoming['contents']+=[{'role':'model','parts':public_parts},
            {'role':'user','parts':[
                {'functionResponse':{'id':frames.calls[1]['id'],'name':'synthetic_tool','response':{'result':10}}},
                {'functionResponse':{'id':'synthetic-call','name':'synthetic_tool','response':{'result':9}}},
            ]}]
        identity={'request_id':'synthetic-request','request_seq':1,'generation':'synthetic-generation'}
        service=Kernel.__new__(Kernel)
        service.lock=threading.RLock();service.cfg={'capture_enabled':False};service.worker_id='synthetic-worker'
        emitted=[];service.output=SimpleNamespace(emit=emitted.append)
        scope=SimpleNamespace(tool_wait_published=True,resume_claimed=False,cancel=threading.Event(),
            native_tool_steps=(3,4),
            value={'gemini_body':body,'request_id':identity['request_id'],'tools':[]},frames=frames,identity=lambda:identity)
        scope.broker=Broker(service,scope,self.root)
        self.addCleanup(scope.broker.close)
        scope.broker.pending[4]={'result':None}
        scope.broker.pending[3]={'result':None}
        service.active=scope
        value={'schema_version':1,'type':'finish_tool_turn',**identity,'body':incoming}
        wrong=copy.deepcopy(value);wrong['body']['contents'][-1]['parts'][0]['functionResponse']['id']='other'
        with self.assertRaises(InputError):service.finish_tool_turn(wrong)
        duplicate = copy.deepcopy(value)
        duplicate['body']['contents'][-1]['parts'][0]['functionResponse']['id'] = call['id']
        with self.assertRaises(InputError):service.finish_tool_turn(duplicate)
        self.assertFalse(scope.resume_claimed)
        mixed = copy.deepcopy(value)
        mixed['body']['contents'][-1]['parts'][0]['functionResponse'].pop('id')
        service.finish_tool_turn(mixed)
        self.assertEqual(scope.broker.pending[3]['result']['structuredContent'],{'result':9})
        self.assertEqual(scope.broker.pending[4]['result']['structuredContent'],{'result':10})
        self.assertEqual(emitted[-1]['type'],'tool_continuation_accepted')
        with self.assertRaises(InputError):service.finish_tool_turn(mixed)

    def test_tool_frames_distinguish_source_repetition_from_equal_parts(self):
        """同一观察身份重投时只消费一次，下一源帧仍有独立原生步骤。@return 无。"""
        def event(epoch, identifier):
            value={'response':{'candidates':[{'content':{'parts':[
                {'functionCall':{'name':'Read','id':identifier,'args':{}}}]}}]}}
            block=b'data: '+json.dumps(value).encode()+b'\n\n'
            return {'call_id':'r-1.1','source':'codeassist_scanner_block','raw_epoch':epoch,
                'data_base64':base64.b64encode(block).decode()}
        frames=Frames()
        self.assertEqual(len(frames.project(event(1,'same'))),1)
        self.assertEqual(frames.project(event(1,'same')),[])
        self.assertEqual(len(frames.project(event(2,'same'))),1)
        self.assertEqual(frames.source_call_ids,['same','same'])
        self.assertEqual(len(frames.call_ids),2)
        with self.assertRaisesRegex(RuntimeError,'native_tool_frame_identity'):
            frames.project(event(2,'changed'))
        with self.assertRaisesRegex(RuntimeError,'invalid_native_tool_id'):
            frames.project(event(3,17))

    def test_legacy_web_search_query_respects_explicit_schema(self):
        """兼容线上空查询声明并保留闭合或自定义属性。@return 无。"""
        for schema, expected in [
                ({},{'query':{'type':'string'}}),
                ({'type':'OBJECT','properties':{}},{'query':{'type':'string'}}),
                ({'type':'object','properties':{},'additionalProperties':False},{}),
                ({'type':'object','properties':{'term':{'type':'string'}}},{'term':{'type':'string'}})]:
            definition={'name':'web_search','parameters':schema}
            body={'tools':[{'functionDeclarations':[definition]}]}
            before=copy.deepcopy(body)
            normalized=gemini_contract.definitions(body,[])[0]['input_schema']
            self.assertEqual(normalized.get('properties',{}),expected)
            self.assertEqual(body,before)

    def test_access_only_document_is_private_and_cannot_overwrite_a_generation(self):
        """业务发布只保存AT，原代次和权威RT保持隔离。@return 无。"""
        home = self.root / 'home'
        result = publish_access_document(home, self.snapshot())
        self.assertEqual(result['credential_generation'], 4)
        value = read_access_document(home)
        self.assertNotIn('refresh_token', value['token'])
        self.assertEqual((home / TOKEN_PATH).stat().st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError):
            publish_access_document(home, self.snapshot())
        value['token']['refresh_token'] = 'synthetic-rt'
        atomic_json(home / TOKEN_PATH, value)
        with self.assertRaises(ValueError):
            read_access_document(home)

    def test_private_read_rejects_links_shared_files_and_parent_links(self):
        """私有读取核对普通文件及整个父目录链。@return 无。"""
        path = self.root / 'private.json'
        atomic_json(path, {'synthetic': True})
        link = self.root / 'link.json'
        link.symlink_to(path)
        with self.assertRaises(OSError):
            read_private(link)
        path.chmod(0o644)
        with self.assertRaises(ValueError):
            read_private(path)
        path.chmod(0o600)
        os.link(path, self.root / 'hardlink.json')
        with self.assertRaises(ValueError):
            read_private(path)
        directory_link = self.root / 'linked'
        directory_link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError):
            read_private(directory_link / 'private.json')

    def test_temperature_and_top_p_use_native_default_without_changing_input(self):
        """兼容字段保留入站记录，执行配置沿原生默认。@return 无。"""
        body = {'contents': [{'role': 'user', 'parts': [{'text': '合成问题'}]}],
            'generationConfig': {'temperature': 0.2, 'topP': 0.8, 'maxOutputTokens': 128}}
        original = copy.deepcopy(body)
        result = gemini_contract.decode_request({'schema_version': 1, 'type': 'gemini_request',
            'request_id': 'synthetic-request', 'model': 'gemini-synthetic', 'body': body}, fixed_model=self.fixed_model)
        self.assertEqual(body, original)
        self.assertEqual(result['native_completion'], {'maxTokens': 128})
        self.assertEqual({item['field'] for item in result['compatibility_notes']},
            {'generationConfig.temperature', 'generationConfig.topP'})

    def test_catalog_selects_real_native_id_for_claude_and_gemini(self):
        """按目录的执行ID选择内核模型，保持账号平台独立。@return 无。"""
        mapping = decode_catalog({'response': json.dumps({'models': {
            'claude-synthetic': {'model': 'MODEL_PLACEHOLDER_M320'},
            'gemini-synthetic': {'model': 'MODEL_PLACEHOLDER_M36'}}})})
        value = gemini_contract.decode_request({'schema_version': 1, 'type': 'gemini_request',
            'request_id': 'claude-request', 'model': 'claude-synthetic', 'native_model': mapping['claude-synthetic'],
            'body': {'contents': [{'parts': [{'text': '合成输入'}]}]}})
        self.assertEqual(value['model'], 'MODEL_PLACEHOLDER_M320')
        with self.assertRaises(ValueError):
            decode_catalog({'response': {'models': {'claude-unknown': {}}}})

    def test_fixed_model_history_reference_roundtrip(self):
        """独立内核以固定映射保存并读回旧协议的历史引用。@return 无。"""
        (self.root / 'histories').mkdir()
        kernel = Kernel.__new__(Kernel)
        kernel.state = self.root
        kernel.fixed_model = self.fixed_model
        kernel.sequence_file = self.root / 'request-sequence.json'
        kernel.cfg = {}
        kernel.lock = threading.RLock()
        kernel.closing = False
        kernel.queued = None
        kernel.active = None
        kernel.seq = 1
        kernel.worker = SimpleNamespace(template=None, bridge=SimpleNamespace(generation='synthetic'))
        kernel.emit = lambda *args, **kwargs: None
        raw = {'schema_version': 1, 'type': 'request', 'request_id': 'fixed-history',
            'prompt': '第二问', 'system': '合成系统提示', 'history': [{'role': 'user', 'text': '第一问'}]}
        first = Scope(request(raw, fixed_model=self.fixed_model), 1, kernel.worker)
        ident, error = kernel.export_history(first, {'trajectoryId': 'fixture', 'steps': [
            {'userInput': {'userResponse': '第一问'}},
            {'plannerResponse': {'response': '第一答'}},
        ]})
        self.assertIsNone(error)
        followup = {'schema_version': 1, 'type': 'request', 'request_id': 'fixed-next',
            'prompt': '第二问', 'history_id': ident}
        with patch('agy_runtime.kernel.threading.Thread'):
            kernel.accept(followup)
        self.assertEqual(kernel.active.value['model'], self.fixed_model[1])
        self.assertEqual(kernel.active.value['system'], raw['system'])
        self.assertEqual(kernel.active.history_count, 2)
        self.assertEqual(kernel.active.value['messages'][-1], {'role': 'assistant', 'text': '第一答'})

    def test_png_directory_uses_verified_model_and_known_flags(self):
        """目录只为已核对的模型报告明确能力。@return 无。"""
        entries = {
            'gemini-yes': {'model': 1, 'supportsImages': False, 'supportedMimeTypes': {'image/png': True}},
            'gemini-no': {'model': 2, 'supportsImages': False},
            'gemini-unknown': {'model': 3},
            'gemini-different': {'model': 4, 'supportsImages': True},
            'gemini-general': {'model': 6, 'supportsImages': True, 'supportedMimeTypes': {'image/png': False}},
        }
        mapping = {'gemini-yes': 1, 'gemini-no': 2, 'gemini-unknown': 3, 'gemini-different': 5, 'gemini-general': 6}
        self.assertEqual(decode_png_support({'response': {'models': entries}}, mapping),
            {'gemini-yes': True, 'gemini-no': False, 'gemini-general': True})

    def test_media_capabilities_do_not_infer_audio_or_video_from_images(self):
        """按实际型号登记各 MIME，图片通用能力只覆盖图片。@return 无。"""
        directory = {'response': {'models': {'gemini-synthetic': {'model': 36, 'supportsImages': True,
            'supportedMimeTypes': {'audio/wav': True, 'video/mp4': False}}}}}
        supported = decode_media_support(directory, {'gemini-synthetic': 36})['gemini-synthetic']
        self.assertTrue(supported['image/jpeg'])
        self.assertTrue(supported['image/gif'])
        self.assertTrue(supported['audio/wav'])
        self.assertFalse(supported['video/mp4'])
        self.assertNotIn('application/pdf', supported)

    def test_gif_frames_preserve_colors_and_request_budget(self):
        """验证缺省原样、启用后首尾帧和同次请求总量。@return 无。"""
        from PIL import Image

        frames = [Image.new('RGB', (16, 16), (i * 20, 20, 220 - i * 20)) for i in range(9)]
        gif = io.BytesIO()
        frames[0].save(gif, format='GIF', save_all=True, append_images=frames[1:], duration=100, disposal=2)
        media = {'inlineData': {'mimeType': 'image/gif', 'data': base64.b64encode(gif.getvalue()).decode()}}
        user = {'role': 'user', 'parts': [media]}
        raw = {'schema_version': 1, 'type': 'gemini_request', 'request_id': 'gif-trial', 'model': 'gemini-synthetic',
               'body': {'contents': [user, user]}}
        output = gemini_contract.decode_request(raw, fixed_model=self.fixed_model)['native_steps']
        self.assertEqual(output[0]['userInput']['media'][0]['inlineData'], media['inlineData']['data'])
        raw['gif_frames'] = True
        output = gemini_contract.decode_request(raw, fixed_model=self.fixed_model)['native_steps']
        for step in output:
            images = step['userInput']['media']
            self.assertEqual([image['mimeType'] for image in images], ['image/png'] * 8)
            for index, original in ((0, frames[0]), (-1, frames[-1])):
                with Image.open(io.BytesIO(base64.b64decode(images[index]['inlineData']))) as frame:
                    self.assertEqual(frame.convert('RGB').getpixel((0, 0)), original.getpixel((0, 0)))
        raw['body']['contents'] = [user] * 17
        with self.assertRaisesRegex(InputError, 'gif_conversion_limit'):
            gemini_contract.decode_request(raw, fixed_model=self.fixed_model)

    def test_model_tool_placeholder_keeps_history_indices(self):
        """验证首次请求可转换带五个空占位的 293 条合成历史。@return 无。"""
        indices = (273, 275, 277, 281, 283)
        contents = [{'role': 'model' if i % 2 else 'user', 'parts': [{'text': str(i)}]} for i in range(293)]
        for i in indices:
            contents[i]['parts'] = [{}, {'functionCall': {'name': 'synthetic_tool', 'args': {'index': i}}}]
            contents[i + 1]['parts'] = [{'functionResponse': {'name': 'synthetic_tool', 'response': {'index': i}}}]
        raw = {'schema_version': 1, 'type': 'gemini_request', 'request_id': 'synthetic-history',
            'model': self.fixed_model[0], 'body': {'contents': contents}}
        original = copy.deepcopy(raw['body'])

        decoded = request(raw, fixed_model=self.fixed_model)

        self.assertEqual(raw['body'], original)
        self.assertEqual(decoded['gemini_body'], original)
        steps = decoded['native_steps']
        self.assertEqual(len(steps), len(contents))
        for i in indices:
            call, = steps[i]['plannerResponse']['toolCalls']
            self.assertEqual(call['id'], f'gemini-history-{i}-1')
            self.assertEqual(steps[i + 1]['metadata']['toolCall'], call)
            self.assertEqual(steps[i + 1]['generic']['result']['resultValue'],
                gemini_contract.native_value({'index': i}))

    def test_history_only_accepts_empty_part_before_single_model_call(self):
        """其他空 Part 和非法调用沿原索引拒绝。@return 无。"""
        call = {'functionCall': {'name': 'synthetic_tool'}}
        for role, parts, error in (
                ('user', [{}, call], 'invalid_gemini_part:/body/contents/0/parts/0'),
                ('model', [{}], 'invalid_gemini_part:/body/contents/0/parts/0'),
                ('model', [{}, {'text': '合成答复'}], 'invalid_gemini_part:/body/contents/0/parts/0'),
                ('model', [call, {}], 'invalid_gemini_part:/body/contents/0/parts/1'),
                ('model', [{}, call, call], 'invalid_gemini_part:/body/contents/0/parts/0'),
                ('model', [{'thought': False}, call], 'invalid_gemini_part:/body/contents/0/parts/0'),
                ('model', [None, call], 'invalid_gemini_object:/body/contents/0/parts/0'),
                ('model', [{}, {'functionCall': None}], 'invalid_gemini_object:/body/contents/0/parts/1/functionCall'),
        ):
            with self.subTest(role=role, parts=parts), self.assertRaisesRegex(InputError, error + '$'):
                gemini_contract.native_history([{'role': role, 'parts': parts}], native_model=self.fixed_model[1])

    def test_legacy_letter_ids_require_prior_history_evidence(self):
        """已观测旧式编号可恢复，普通纯字母名称单独出现时仍拒绝。@return 无。"""
        call = {'role': 'model', 'parts': [{'functionCall': {'name': 'synthetic_lookup', 'args': {}}}]}
        ids = ['V7rd5Z9q', 'QvKrmPax', 'call_' + 'a1f0' * 8]
        replies = [{'role': 'user', 'parts': [{'functionResponse': {'name': alias, 'response': {}}}]} for alias in ids]
        turns = [turn for reply in replies for turn in (call, reply)]
        steps = gemini_contract.native_history(turns, native_model=self.fixed_model[1])
        self.assertEqual([step['metadata']['toolCall']['id'] for step in steps if 'generic' in step], ids)
        with self.assertRaisesRegex(InputError, 'ambiguous_or_unknown_function_response'):
            gemini_contract.native_history(turns[2:4], native_model=self.fixed_model[1])

    def test_legacy_tool_history_reconstructs_unambiguous_calls_and_keeps_input(self):
        """旧格式按相邻单轮恢复，多个或冲突的历史给出拒绝。@return 无。"""
        call = {'functionCall': {'name': 'synthetic_tool', 'args': {'value': 1}}}
        reply = {'functionResponse': {'name': 'call_123', 'response': {'success': True}}}
        contents = [{'role': 'model', 'parts': [{}, call]}, {'role': 'user', 'parts': [reply]}]
        original = copy.deepcopy(contents)
        steps = gemini_contract.native_history(contents, native_model=self.fixed_model[1])
        self.assertEqual(contents, original)
        original_call = steps[0]['plannerResponse']['toolCalls'][0]
        self.assertEqual(original_call['id'], 'call_123')
        self.assertEqual(original_call['name'], 'synthetic_tool')
        self.assertEqual(steps[1]['metadata']['toolCall'], original_call)
        for invalid in (contents * 2, [{**contents[0], 'parts': [call, call]}, contents[1]],
                [contents[0], {'role': 'user', 'parts': [{'text': '间隔'}]}, contents[1]]):
            with self.assertRaisesRegex(InputError, 'function_response'):
                gemini_contract.native_history(invalid, native_model=self.fixed_model[1])
        with self.assertRaisesRegex(InputError, 'ambiguous_or_unknown_function_response'):
            gemini_contract.native_history(contents, ['call_123'], native_model=self.fixed_model[1])

    def test_mixed_tool_history_pairs_results_across_user_contents(self):
        """历史和实时回填按工具名补齐，并保留稍后收到的显式 ID。@return 无。"""
        names = ('synthetic_lookup', 'synthetic_tool', 'synthetic_tool', 'synthetic_tool')
        calls = [{'name': name, 'id': f'call-{index}', 'args': {'index': index}}
            for index, name in enumerate(names)]
        previous = {'contents': [{'role': 'user', 'parts': [{'text': '合成问题'}]}]}
        expected = [{'value': index} for index in range(len(calls))]
        for sequence, with_id in (((1, 2, 3, 0), False), ((2, 1, 3, 0), True)):
            with self.subTest(with_id=with_id):
                model_parts = [{'functionCall': {'name': call['name'], 'args': copy.deepcopy(call['args'])}}
                    for call in calls]
                replies = [{'functionResponse': {'name': names[index], 'response': copy.deepcopy(expected[index])}}
                    for index in sequence]
                if with_id:
                    model_parts[1]['functionCall']['id'] = calls[1]['id']
                    replies[1]['functionResponse']['id'] = calls[1]['id']
                model = {'role': 'model', 'parts': model_parts}
                contents = [*previous['contents'], model, {'role': 'user', 'parts': replies}]
                original = copy.deepcopy(contents)
                self.assertEqual(gemini_contract.continuation_results(previous, calls, {'contents': contents}), expected)
                history = [*contents[:-1], {'role': 'user', 'parts': replies[:1]},
                    {'role': 'user', 'parts': replies[1:]}]
                steps = gemini_contract.native_history(history, native_model=self.fixed_model[1])
                generic = [step['generic'] for step in steps if 'generic' in step]
                self.assertEqual([step['args']['index'] for step in generic], ['0', '1', '2', '3'])
                self.assertEqual([step['result']['resultValue'] for step in generic],
                    [gemini_contract.native_value(value) for value in expected])
                self.assertEqual(contents, original)

    def test_split_frames_preserve_parts_signature_extensions_and_single_usage(self):
        """兼容投影保留所有Part，并只在最后一帧发布终态与用量。@return 无。"""
        body = {'candidates': [{'index': 0, 'content': {'role': 'model', 'parts': [
            {'text': '合成思考', 'thought': True, 'thoughtSignature': 'c2ln'}, {'text': '合成回答'}]},
            'finishReason': 'STOP', 'syntheticExtension': True}], 'usageMetadata': {'totalTokenCount': 7},
            'modelVersion': 'synthetic-model-version'}
        source = {'data_base64': base64.b64encode(json.dumps(body).encode()).decode(), 'raw_epoch': 1}
        result = Frames().project(source)
        decoded = [json.loads(base64.b64decode(item['data_base64'])) for item in result]
        self.assertEqual([item['candidates'][0]['content']['parts'][0] for item in decoded], body['candidates'][0]['content']['parts'])
        self.assertNotIn('usageMetadata', decoded[0])
        self.assertEqual(decoded[-1]['usageMetadata'], body['usageMetadata'])
        self.assertTrue(all(item['candidates'][0]['syntheticExtension'] for item in decoded))

    def test_gemini_history_normalizes_thought_signature_encoding(self):
        """工具和思考签名兼容双字母表与缺省填充，原字节保持一致。@return 无。"""
        for signature in ('+/8=', '+/8', '-_8=', '-_8'):
            with self.subTest(signature=signature):
                turns = [
                    {'role': 'model', 'parts': [
                        {'text': '合成思考', 'thought': True, 'thoughtSignature': signature},
                        {'functionCall': {'name': 'synthetic_tool', 'id': 'synthetic-id'}, 'thoughtSignature': signature},
                    ]},
                    {'role': 'user', 'parts': [{'functionResponse': {
                        'name': 'synthetic_tool', 'id': 'synthetic-id', 'response': {'ok': True},
                    }}]},
                ]
                original = copy.deepcopy(turns)
                plan, reply = gemini_contract.native_history(turns, native_model=self.fixed_model[1])
                planner = plan['plannerResponse']
                self.assertEqual(planner['thinkingSignature'], '+/8=')
                self.assertEqual(planner['toolCalls'][0]['thinkingSignature'], '+/8=')
                self.assertEqual(reply['metadata']['toolCall']['thinkingSignature'], '+/8=')
                self.assertEqual(turns, original)
        for malformed in ('', '-+8=', '-_8==', 'A', 'bad%'):
            with self.subTest(malformed=malformed), self.assertRaisesRegex(InputError, 'invalid_gemini_thought_signature'):
                gemini_contract.call_signature(malformed, {})

    def test_oauth_scanner_envelope_preserves_frames_and_authentication_errors(self):
        """真实OAuth逻辑块解开信封并保留签名、扩展和认证错误。@return 无。"""
        frame={'candidates':[{'content':{'role':'model','parts':[{'text':'合成回答','thoughtSignature':'c2ln'}]},
            'finishReason':'STOP','syntheticExtension':True}],'usageMetadata':{'totalTokenCount':7}}
        for envelope,expected in [({'response':frame,'traceId':'synthetic-trace'},frame),
                ({'error':{'code':401,'status':'UNAUTHENTICATED'}},{'error':{'code':401,'status':'UNAUTHENTICATED'}})]:
            raw=('data: '+json.dumps(envelope)+'\n\n').encode()
            event={'source':'codeassist_scanner_block','data_base64':base64.b64encode(raw).decode()}
            result=Frames().project(event)
            self.assertEqual(json.loads(base64.b64decode(result[0]['data_base64'])),expected)
            self.assertEqual(base64.b64decode(event['data_base64']),raw)
        for raw in [b': keepalive\n\n',b'event: message\n\n']:
            self.assertEqual(Frames().project({'source':'codeassist_scanner_block','data_base64':base64.b64encode(raw).decode()}),[])

    def test_source_terminal_requires_finish_or_actual_safety_block(self):
        """文本、usage和错误单独出现不能冒充成功终态，安全拦截保留来源。@return 无。"""
        for frame,terminal in [
                ({'candidates':[{'content':{'parts':[{'text':'部分回答'}]}}]},False),
                ({'usageMetadata':{'totalTokenCount':7}},False),
                ({'error':{'code':429}},False),
                ({'promptFeedback':{'blockReason':False}},False),
                ({'candidates':[{'finishReason':'FINISH_REASON_UNSPECIFIED'}]},False),
                ({'candidates':[{'finishReason':'STOP'}]},True),
                ({'candidates':[{'finishReason':'MAX_TOKENS'}]},True),
                ({'promptFeedback':{'blockReason':'SAFETY'}},True)]:
            frames=Frames()
            frames.project({'data_base64':base64.b64encode(json.dumps(frame).encode()).decode()})
            self.assertEqual(frames.terminal,terminal)

    def test_tool_continuation_checks_history_arguments_and_explicit_ids(self):
        """工具续轮保持原历史和真实调用归属，拒绝改写与错ID。@return 无。"""
        previous = {'contents': [
            {'role': 'user', 'parts': [{'text': '合成问题'}]},
            {'role': 'model', 'parts': [{}, {'functionCall': {'name': 'synthetic_tool', 'id': 'earlier-call'}}]},
            {'role': 'user', 'parts': [{'functionResponse': {'name': 'synthetic_tool', 'id': 'earlier-call', 'response': {}}}]},
        ]}
        call = {'name': 'synthetic_tool', 'args': {'value': 1}, 'id': 'synthetic-call'}
        incoming = copy.deepcopy(previous)
        incoming['contents'] += [{'role': 'model', 'parts': [{}, {'functionCall': copy.deepcopy(call)}]},
            {'role': 'user', 'parts': [{'functionResponse': {'name': 'synthetic_tool', 'id': 'synthetic-call',
                'response': {'value': '合成结果'}}}]}]
        self.assertEqual(gemini_contract.continuation_results(previous, [call], incoming),
            [{'value': '合成结果'}])
        continuation = copy.deepcopy(incoming)
        continuation['contents'].append({'role':'user','parts':[{'text':'收到结果后继续'}]})
        self.assertEqual(gemini_contract.continuation_results(previous, [call], continuation),
            [{'value':'合成结果'}])
        raw = {'schema_version': 1, 'type': 'gemini_request', 'request_id': 'synthetic-continuation',
            'model': self.fixed_model[0], 'body': continuation}
        decoded = request(raw, fixed_model=self.fixed_model)
        self.assertEqual(decoded['gemini_body'], continuation)
        steps = decoded['native_steps']
        self.assertEqual(steps[-2]['type'], 'CORTEX_STEP_TYPE_GENERIC')
        self.assertEqual(steps[-2]['metadata']['toolCall']['id'], 'synthetic-call')
        self.assertEqual(steps[-1]['userInput']['userResponse'], '收到结果后继续')
        rewritten = copy.deepcopy(incoming)
        rewritten['contents'][1]['parts'].pop(0)
        with self.assertRaisesRegex(InputError, 'gemini_pending_history_mismatch'):
            gemini_contract.continuation_results(previous, [call], rewritten)
        rewritten = copy.deepcopy(incoming)
        rewritten['contents'][-2]['parts'][1]['functionCall']['args']['value'] = 2
        with self.assertRaisesRegex(InputError, 'gemini_pending_call_mismatch'):
            gemini_contract.continuation_results(previous, [call], rewritten)
        incoming['contents'][-1]['parts'][0]['functionResponse']['name'] = 'old-result-name'
        self.assertEqual(gemini_contract.continuation_results(previous, [call], incoming),
            [{'value': '合成结果'}])
        result = incoming['contents'][-1]['parts'][0]['functionResponse']
        result.pop('id')
        result['name'] = 'synthetic-call'
        self.assertEqual(gemini_contract.continuation_results(previous, [call], incoming),
            [{'value': '合成结果'}])
        incoming['contents'][-1]['parts'][0]['functionResponse']['id'] = 'wrong-call'
        with self.assertRaises(InputError):
            gemini_contract.continuation_results(previous, [call], incoming)
        incoming['contents'][0]['parts'][0]['text'] = '改写后的历史'
        with self.assertRaises(InputError):
            gemini_contract.continuation_results(previous, [call], incoming)

    def test_parallel_same_name_gemini_results_keep_original_call_order(self):
        """双 Read 的 ID 被中转移除后，历史和活跃工具轮仍按原参数绑定。@return 无。"""
        calls = [{'name': 'Read', 'id': f'call-{i}', 'args': {'path': f'{i}.txt'}} for i in range(2)]
        previous = {'contents': [{'role': 'user', 'parts': [{'text': '读取两个文件'}]}]}
        model = {'role': 'model', 'parts': [{'functionCall': {'name': call['name'], 'args': call['args']}}
            for call in calls]}
        values = [{'content': '文件甲'}, {'content': '文件乙'}]
        results = {'role': 'user', 'parts': [{'functionResponse': {'name': 'Read', 'response': value}}
            for value in values]}
        incoming = {'contents': [*previous['contents'], model, results]}
        self.assertEqual(gemini_contract.continuation_results(previous, calls, incoming), values)
        generic = [step for step in gemini_contract.native_history(incoming['contents'], native_model=self.fixed_model[1]) if 'generic' in step]
        self.assertEqual([step['generic']['args']['path'] for step in generic], ['0.txt', '1.txt'])
        self.assertEqual([step['generic']['result']['resultValue'] for step in generic],
            [gemini_contract.native_value(value) for value in values])

        for index, part in enumerate(results['parts']):
            part['functionResponse']['id'] = calls[index]['id']
            model['parts'][index]['functionCall']['id'] = calls[index]['id']
        results['parts'].reverse()
        self.assertEqual(gemini_contract.continuation_results(previous, calls, incoming), values)
        results['parts'][0]['functionResponse']['id'] = calls[0]['id']
        with self.assertRaisesRegex(InputError, 'gemini_pending_results_mismatch'):
            gemini_contract.continuation_results(previous, calls, incoming)

    def test_oauth_startup_has_no_test_api_key_or_custom_ca_and_closes_failed_launch(self):
        """正式启动采用OAuth HOME，Popen失败也收回管道与FIFO。@return 无。"""
        bridge = NativeBridge(self.root / 'worker')
        self.addCleanup(bridge.events.close)
        bridge.native_home = self.root / 'home'
        bridge.binary = self.root / 'synthetic-binary'
        bridge.proxy_url = 'http://synthetic-proxy.example.test:8080'
        observed = {}

        def launch(args, **kwargs):
            """捕获正式环境并在启动前注入失败。@param args 启动参数。@param kwargs 环境。@return 无。"""
            observed.update(kwargs['env'])
            raise OSError('合成启动失败')

        with patch('agy_runtime.native_bridge.verify_binary'), patch('agy_runtime.native_bridge.subprocess.Popen', side_effect=launch):
            for checkpoint in (False,True):
                bridge.checkpoint_enabled=checkpoint
                observed.clear()
                with self.assertRaises(OSError):
                    bridge._start()
                self.assertEqual(observed.get('GODEBUG'),'multipathtcp=0' if checkpoint else None)
        self.assertNotIn('GEMINI_API_KEY', observed)
        self.assertNotIn('SSL_CERT_FILE', observed)
        self.assertEqual(observed['HOME'], str(bridge.native_home))
        self.assertEqual(observed['HTTPS_PROXY'], bridge.proxy_url)
        self.assertFalse(bridge.input_fifo.exists())
        with self.assertRaises(OSError):
            os.fstat(bridge.event_r)

    def test_protocol_output_is_ordered_and_anonymous_by_default(self):
        """私有协议只向消费者交付，默认匿名暂存不保留请求归档。@return 无。"""
        stream = io.BytesIO()
        with patch('agy_runtime.storage.sys.stdout', SimpleNamespace(buffer=stream)):
            output = Output()
            output.emit({'type': 'worker_ready', 'generation': 'synthetic-generation'})
            output.emit({'type': 'completed', 'request_id': 'synthetic-request'})
            output.close()
        events = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual([item['type'] for item in events], ['worker_ready', 'completed'])
        self.assertFalse(output.archive)
        self.assertTrue(output.writer.closed)

    def test_oauth_configuration_rejects_test_key_and_reads_access_only_home(self):
        """正式配置保留管理归属，测试API Key受到拒绝。@return 无。"""
        home = self.root / 'home'
        home.mkdir(mode=0o700)
        publish_access_document(home, self.snapshot())
        value = {'home': str(home), 'public_model': 'gemini-synthetic',
            'native_model': 'MODEL_PLACEHOLDER_M36', 'binary_path': '/synthetic/agy',
            'account_id': 17, 'credential_generation': 4}
        path = self.root / 'config.json'
        atomic_json(path, value)
        self.assertEqual(config(path)['credential_generation'], 4)
        value['api_key'] = 'synthetic-key'
        atomic_json(path, value)
        with self.assertRaises(ValueError):
            config(path)


if __name__ == '__main__':
    unittest.main()
