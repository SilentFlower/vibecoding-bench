"""使用合成凭据及真实文件核对AGY原生运行边界，模型提交为零。"""
import base64
import copy
import gzip
import json
import io
import os
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener
from unittest.mock import patch
from types import SimpleNamespace

from agy_runtime import gemini_contract
from agy_runtime.contract import InputError
from agy_runtime.credentials import TOKEN_PATH, publish_access_document, read_access_document, read_private
from agy_runtime.gemini_frames import Frames
from agy_runtime.models import configure_model, decode_catalog, decode_media_support, decode_png_support
from agy_runtime.native_bridge import NativeBridge
from agy_runtime.process_memory import cgroup_memory
from agy_runtime.safety_egress import MODEL_PATH, SafetyEgress, _Request
from agy_runtime.kernel import Bridge, Kernel, Worker
from agy_runtime.stream_controller import NativeJob
from agy_runtime.tool_broker import Broker
from agy_runtime.storage import Output, config
from runtime_files import atomic_json


class AgyRuntimeTests(unittest.TestCase):
    """验证协议语义、账号凭据及原生启动环境。"""

    def setUp(self):
        """建立独立私有文件根及固定模型。@return 无。"""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        configure_model('gemini-synthetic', 'MODEL_PLACEHOLDER_M36')

    def snapshot(self):
        """创建同代AT-only管理快照。@return 合成快照。"""
        return {'account_id': 17, 'credential_generation': 4, 'access_token': 'synthetic-at',
            'expires_at': int((datetime.now(timezone.utc) + timedelta(hours=2)).timestamp() * 1000),
            'email': 'synthetic@example.test'}

    def test_foreign_cascade_does_not_change_completed_model_stream(self):
        """不同 Cascade 的迟到事件隔离，同 Cascade 的第二次启动仍计数。@return 无。"""
        bridge=Bridge.__new__(Bridge)
        worker=Worker.__new__(Worker)
        recorded=[]
        worker.owner=SimpleNamespace(emit=lambda kind, **fields: recorded.append(kind))
        scope=SimpleNamespace(worker=worker,route='r-1',root='owned',foreign_call_id=None,
            value={'request_format':'gemini'},frames=Frames(),identity=lambda: {},tls_trace=None,safety_egress=None)
        worker.owner.active=scope
        bridge.worker=worker
        bridge.events=io.StringIO();bridge.errors=[];bridge.source_events=0
        bridge.active_job=scope.job=NativeJob(scope.route,SimpleNamespace(offer=lambda event: True))
        owned={'event':'model_start','request_id':scope.route,'call_id':'r-1.1','ns':1,
            'native_context':{'ConversationID':'owned'}}
        foreign={**owned,'call_id':'r-1.2','native_context':{'ConversationID':'other'}}
        bridge._emit(owned)
        with self.assertRaisesRegex(RuntimeError,'native_root_identity'):
            bridge._emit(foreign)
        frame=json.dumps({'candidates':[{'finishReason':'STOP'}]}).encode()
        bridge._emit({**owned,'event':'gemini_response','data_base64':base64.b64encode(frame).decode()})
        bridge._emit({**owned,'event':'model_end','native_error_present':None})
        bridge._emit(foreign)
        bridge._emit({**foreign,'event':'gemini_response','data_base64':'外部帧禁止解析'})
        bridge._emit({**foreign,'event':'model_end','native_error_present':None})
        self.assertEqual(recorded,['model_start','gemini_response','model_end','foreign_model_observed'])
        self.assertEqual((scope.job.calls,scope.job.ends),(1,1))
        self.assertTrue(scope.job.ended.is_set())
        bridge._emit({**owned,'call_id':'r-1.3'})
        self.assertEqual(scope.job.calls,2)

    def test_gemini_text_modality_uses_native_default(self):
        """确认显式文本输出沿用默认行为，图片和音频仍保留字段级错误。@return 无。"""
        raw = {'schema_version': 1, 'type': 'gemini_request', 'request_id': 'modalities',
               'model': 'gemini-synthetic', 'body': {'contents': [{'parts': [{'text': '合成请求'}]}]}}
        expected = gemini_contract.decode_request(raw)['native_completion']
        for modalities in ([], ['TEXT']):
            raw['body']['generationConfig'] = {'responseModalities': modalities}
            self.assertEqual(gemini_contract.decode_request(raw)['native_completion'], expected)
        for modalities in (None, 'TEXT', ['IMAGE'], ['TEXT', 'AUDIO']):
            raw['body']['generationConfig'] = {'responseModalities': modalities}
            with self.subTest(modalities=modalities), self.assertRaisesRegex(
                    InputError, 'unsupported_gemini_output_modality:/body/generationConfig/responseModalities'):
                gemini_contract.decode_request(raw)

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
        from agy_runtime.supervisor import Supervisor
        for budget,actual in [(0,None),(768,None),(768,1024),(0,805306368)]:
            with patch('agy_runtime.supervisor.cgroup_memory',return_value={'max_bytes':actual}), patch('agy_runtime.supervisor.ImagePool') as pool:
                with self.assertRaisesRegex(ValueError,'冻结RAM预算'):
                    Supervisor({'memory_mib':budget})
                pool.assert_not_called()

    def test_kernel_completion_reaches_real_tool_broker_once(self):
        """真实Kernel与Broker方法接线把结果交还原待处理项，错误ID和重复回填拒绝。@return 无。"""
        body={'contents':[{'role':'user','parts':[{'text':'合成问题'}]}]}
        call={'id':'synthetic-call','name':'synthetic_tool','args':{'x':1}}
        incoming=copy.deepcopy(body)
        incoming['contents']+=[{'role':'model','parts':[{'functionCall':call}]},
            {'role':'user','parts':[{'functionResponse':{'id':'synthetic-call','name':'synthetic_tool','response':{'result':9}}}]}]
        identity={'request_id':'synthetic-request','request_seq':1,'generation':'synthetic-generation'}
        service=Kernel.__new__(Kernel)
        service.lock=threading.RLock();service.cfg={'capture_enabled':False};service.worker_id='synthetic-worker'
        emitted=[];service.output=SimpleNamespace(emit=emitted.append)
        scope=SimpleNamespace(tool_wait_published=True,resume_claimed=False,cancel=threading.Event(),
            value={'gemini_body':body,'request_id':identity['request_id'],'tools':[]},frames=SimpleNamespace(calls=[call]),identity=lambda:identity)
        scope.broker=Broker(service,scope,self.root)
        self.addCleanup(scope.broker.close)
        scope.broker.pending['synthetic-native-call']={'native_call':{'name':'synthetic_tool'},'result':None}
        service.active=scope
        value={'schema_version':1,'type':'finish_tool_turn',**identity,'body':incoming}
        wrong=copy.deepcopy(value);wrong['body']['contents'][-1]['parts'][0]['functionResponse']['id']='other'
        with self.assertRaises(InputError):service.finish_tool_turn(wrong)
        self.assertFalse(scope.resume_claimed)
        service.finish_tool_turn(value)
        self.assertEqual(scope.broker.pending['synthetic-native-call']['result']['structuredContent'],{'result':9})
        self.assertEqual(emitted[-1]['type'],'tool_continuation_accepted')
        with self.assertRaises(InputError):service.finish_tool_turn(value)

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
            'request_id': 'synthetic-request', 'model': 'gemini-synthetic', 'body': body})
        self.assertEqual(body, original)
        self.assertEqual(result['native_completion'], {'maxTokens': 128})
        self.assertEqual({item['field'] for item in result['compatibility_notes']},
            {'generationConfig.temperature', 'generationConfig.topP'})

    def test_catalog_selects_real_native_id_for_claude_and_gemini(self):
        """按目录的执行ID选择内核模型，保持账号平台独立。@return 无。"""
        mapping = decode_catalog({'response': json.dumps({'models': {
            'claude-synthetic': {'model': 'MODEL_PLACEHOLDER_M320'},
            'gemini-synthetic': {'model': 'MODEL_PLACEHOLDER_M36'}}})})
        configure_model('claude-synthetic', mapping['claude-synthetic'])
        value = gemini_contract.decode_request({'schema_version': 1, 'type': 'gemini_request',
            'request_id': 'claude-request', 'model': 'claude-synthetic',
            'body': {'contents': [{'parts': [{'text': '合成输入'}]}]}})
        self.assertEqual(value['model'], 'MODEL_PLACEHOLDER_M320')
        with self.assertRaises(ValueError):
            decode_catalog({'response': {'models': {'claude-unknown': {}}}})

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
        output = gemini_contract.decode_request(raw)['native_steps']
        self.assertEqual(output[0]['userInput']['media'][0]['inlineData'], media['inlineData']['data'])
        raw['gif_frames'] = True
        output = gemini_contract.decode_request(raw)['native_steps']
        for step in output:
            images = step['userInput']['media']
            self.assertEqual([image['mimeType'] for image in images], ['image/png'] * 8)
            for index, original in ((0, frames[0]), (-1, frames[-1])):
                with Image.open(io.BytesIO(base64.b64decode(images[index]['inlineData']))) as frame:
                    self.assertEqual(frame.convert('RGB').getpixel((0, 0)), original.getpixel((0, 0)))
        raw['body']['contents'] = [user] * 17
        with self.assertRaisesRegex(InputError, 'gif_conversion_limit'):
            gemini_contract.decode_request(raw)

    def test_legacy_letter_ids_require_prior_history_evidence(self):
        """已观测旧式编号可恢复，普通纯字母名称单独出现时仍拒绝。@return 无。"""
        call = {'role': 'model', 'parts': [{'functionCall': {'name': 'synthetic_lookup', 'args': {}}}]}
        ids = ['V7rd5Z9q', 'QvKrmPax', 'call_' + 'a1f0' * 8]
        replies = [{'role': 'user', 'parts': [{'functionResponse': {'name': alias, 'response': {}}}]} for alias in ids]
        turns = [turn for reply in replies for turn in (call, reply)]
        steps = gemini_contract.native_history(turns)
        self.assertEqual([step['metadata']['toolCall']['id'] for step in steps if 'generic' in step], ids)
        with self.assertRaisesRegex(InputError, 'ambiguous_or_unknown_function_response'):
            gemini_contract.native_history(turns[2:4])

    def test_legacy_tool_history_reconstructs_unambiguous_calls_and_keeps_input(self):
        """旧格式按相邻单轮恢复，多个或冲突的历史给出拒绝。@return 无。"""
        call = {'functionCall': {'name': 'synthetic_tool', 'args': {'value': 1}}}
        reply = {'functionResponse': {'name': 'call_123', 'response': {'success': True}}}
        contents = [{'role': 'model', 'parts': [call]}, {'role': 'user', 'parts': [reply]}]
        original = copy.deepcopy(contents)
        steps = gemini_contract.native_history(contents)
        self.assertEqual(contents, original)
        original_call = steps[0]['plannerResponse']['toolCalls'][0]
        self.assertEqual(original_call['id'], 'call_123')
        self.assertEqual(original_call['name'], 'synthetic_tool')
        self.assertEqual(steps[1]['metadata']['toolCall'], original_call)
        for invalid in (contents * 2, [{**contents[0], 'parts': [call, call]}, contents[1]],
                [contents[0], {'role': 'user', 'parts': [{'text': '间隔'}]}, contents[1]]):
            with self.assertRaisesRegex(InputError, 'function_response'):
                gemini_contract.native_history(invalid)
        with self.assertRaisesRegex(InputError, 'ambiguous_or_unknown_function_response'):
            gemini_contract.native_history(contents, ['call_123'])

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
                plan, reply = gemini_contract.native_history(turns)
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
        previous = {'contents': [{'role': 'user', 'parts': [{'text': '合成问题'}]}]}
        call = {'name': 'synthetic_tool', 'args': {'value': 1}, 'id': 'synthetic-call'}
        incoming = copy.deepcopy(previous)
        incoming['contents'] += [{'role': 'model', 'parts': [{'functionCall': copy.deepcopy(call)}]},
            {'role': 'user', 'parts': [{'functionResponse': {'name': 'synthetic_tool', 'id': 'synthetic-call',
                'response': {'value': '合成结果'}}}]}]
        self.assertEqual(gemini_contract.continuation_results(previous, [call], incoming),
            {'synthetic_tool': {'value': '合成结果'}})
        incoming['contents'][-1]['parts'][0]['functionResponse']['name'] = 'old-result-name'
        self.assertEqual(gemini_contract.continuation_results(previous, [call], incoming),
            {'synthetic_tool': {'value': '合成结果'}})
        result = incoming['contents'][-1]['parts'][0]['functionResponse']
        result.pop('id')
        result['name'] = 'synthetic-call'
        self.assertEqual(gemini_contract.continuation_results(previous, [call], incoming),
            {'synthetic_tool': {'value': '合成结果'}})
        incoming['contents'][-1]['parts'][0]['functionResponse']['id'] = 'wrong-call'
        with self.assertRaises(InputError):
            gemini_contract.continuation_results(previous, [call], incoming)
        incoming['contents'][0]['parts'][0]['text'] = '改写后的历史'
        with self.assertRaises(InputError):
            gemini_contract.continuation_results(previous, [call], incoming)

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
            with self.assertRaises(OSError):
                bridge._start()
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
