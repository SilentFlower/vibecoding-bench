"""从普通 Messages 客户端验证默认发行网关、账号发送器和同账号 Unix 事件源。"""
from __future__ import annotations

import json
import socket
import sys
from contextlib import closing
from hashlib import sha256
from http.client import HTTPConnection
from pathlib import Path
from struct import pack
from subprocess import Popen
from uuid import UUID, uuid4

from verify_tui_sender_actions import SOURCE, response_parts, wait_for


def public_stream(token: str, body: dict, result: str | None = None, while_paused=None) -> tuple[list[dict], int]:
    """在读取首个增量后放行事件源，再比对完整原始字节。
    @param token 合成公开令牌。@param body 普通 Messages 请求。@param result 续轮文本。
    @param while_paused 收到首段且发送器占槽期间的测试动作。@return 客户端事件和首段字节数。
    """
    wire = json.dumps(body, ensure_ascii=False).encode()
    with closing(HTTPConnection('127.0.0.1', 18090, timeout=8)) as client:
        client.request('POST', '/v1/messages', wire, headers={
            'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json',
            'User-Agent': 'flower-tui-sender-status/1'})
        with client.getresponse() as response:
            assert response.status == 200, (response.status, response.read())
            assert response.getheader('Content-Type').startswith('text/event-stream')
            first = bytearray()
            identifier = None
            while True:
                line = response.readline()
                assert line, '首个增量之前连接已结束'
                first.extend(line)
                if not line.startswith(b'data:'):
                    continue
                event = json.loads(line[5:])
                if event['type'] == 'message_start':
                    identifier = str(UUID(event['message']['id'].removeprefix('msg_')))
                if event['type'] == 'content_block_delta':
                    break
            assert identifier is not None
            delimiter = response.readline()
            assert delimiter == b'\n'
            first.extend(delimiter)
            expected, tail = response_parts(identifier, body['model'], result)
            release = SOURCE / f'{identifier}.release'
            try:
                wait_for((SOURCE / f'{identifier}.paused').exists, '事件源未停在分片中间')
                assert not release.exists() and first == expected
                assert (SOURCE / f'{identifier}.prepared').read_text() == sha256(wire).hexdigest()
                if while_paused:
                    while_paused()
            finally:
                release.touch()
            observed = response.read()
            assert observed == tail
            assert (SOURCE / f'{identifier}.submits').read_text().splitlines() == ['1']
    return [json.loads(line[5:]) for line in (first + observed).splitlines() if line.startswith(b'data:')], len(first)


def check_public_gateway(binding, write_config, proxy, control, admin_call, http, token, ledger: Path, set_runtime,
                         verify_cache) -> dict:
    """通过管理 API 启用普通账号，再从公开 Messages 入口完成双轮屏障及归属验证。
    @param binding 当前账号登记。@param write_config 配置写入器。@param proxy 隔离代理。
    @param control 发送器状态读取器。@param admin_call 管理 API。@param http 本地 HTTP 客户端。
    @param token 普通客户端令牌。@param ledger 本地验收卷内的发送器提交记录。
    @param set_runtime 设置合成运行环境的代次和休眠状态。@param verify_cache 以同一账号快照比较缓存。
    @return 脱敏验证结果。
    """
    source = Popen([sys.executable, str(Path(__file__).with_name('verify_tui_sender_actions.py')), '--source'],
                   user=1001, group=1001, extra_groups=[])
    try:
        write_config(binding, proxy, tui_v2={'max_reservations': 3})
        wait_for(lambda: control()[1]['tui_v2'].get('ready') is True, '公开测试发送器未就绪')
        set_runtime(binding['generation'], True)
        detail = admin_call('GET', 'accounts/1', None)
        assert detail['request_backend'] == 'legacy' and detail['tui_v2_available'] is False, detail.keys()
        assert admin_call('GET', 'accounts/1', None)['tui_v2_available'] is False
        selected = admin_call('PUT', 'accounts/1', {'request_backend': 'tui_v2',
                              'request_backend_revision': detail['request_backend_revision']})
        assert selected['request_backend'] == 'tui_v2' and selected['request_backend_pending'] is None
        foreign = admin_call('POST', 'tokens', {'name': '独立调用方', 'allowed_accounts': '1'})['token']
        generation = binding['generation'] + 1
        set_runtime(generation, True)
        sleeping = admin_call('GET', 'accounts/1', None)
        assert sleeping['request_backend'] == 'tui_v2' and sleeping['tui_v2_available'] is False
        # 此隔离数据库显式配置已实测支持行内 system 的联调模型，沿用产品模型准入规则。
        admin_call('PUT', 'settings', {'allow_system_role_models': 'deepseek-flash'})
        history = [{'role': 'user', 'content': '使用本地测试工具 ' + uuid4().hex},
                   {'role': 'system', 'content': [{'type': 'text', 'text': '保留首轮原始上下文'}]}]
        body = {'model': 'deepseek-flash', 'stream': True, 'max_tokens': 128, 'messages': history,
                'tools': [{'name': 'LocalFixture', 'description': '读取合成样本', 'input_schema': {
                    'type': 'object', 'properties': {'sample': {'type': 'string'}}, 'required': ['sample']}}]}
        existing = set(SOURCE.glob('*.submits'))
        events, first_size = public_stream(token, body)
        tool, = [e['content_block'] for e in events if e['type'] == 'content_block_start']
        assert tool['name'] == 'LocalFixture'
        tool['input'] = json.loads(''.join(e['delta']['partial_json'] for e in events if e['type'] == 'content_block_delta'))
        result = '客户端读取的合成结果-' + uuid4().hex
        replies = [{'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': tool['id'], 'content': result}]},
                   {'role': 'system', 'content': [{'type': 'text', 'text': '续轮附加上下文'}]}]
        follow = {**body, 'messages': [*history, {'role': 'assistant', 'content': [tool]}, *replies]}
        prepared = set(SOURCE.glob('*.prepared'))
        denied, _ = http(18090, 'POST', '/v1/messages', foreign, follow)
        assert denied == 400 and set(SOURCE.glob('*.prepared')) == prepared, denied
        altered = {**follow, 'messages': [*history, {'role': 'assistant', 'content': [
            {**tool, 'input': {'sample': '其他样本'}}]}, *replies]}
        mismatch, _ = http(18090, 'POST', '/v1/messages', token, altered)
        assert mismatch == 400 and set(SOURCE.glob('*.prepared')) == prepared, mismatch
        set_runtime(generation, True)
        try:
            missing, _ = http(18090, 'POST', '/v1/messages', token, follow)
            assert missing == 503 and set(SOURCE.glob('*.prepared')) == prepared, missing
        finally:
            set_runtime(generation, False)
        set_runtime(generation + 1, False)
        try:
            wrong_generation, _ = http(18090, 'POST', '/v1/messages', token, follow)
            assert wrong_generation == 503 and set(SOURCE.glob('*.prepared')) == prepared, wrong_generation
        finally:
            set_runtime(generation, False)

        def disconnect_queued_request():
            # 续轮已经占有唯一 HTTP 槽。在新轮预留成功后断开公开连接，必须实际送达 cancel。
            before = set(SOURCE.glob('*.prepared'))
            with closing(HTTPConnection('127.0.0.1', 18090, timeout=5)) as queued:
                new = {**body, 'messages': [{'role': 'user', 'content': '客户端将主动断开 ' + uuid4().hex}]}
                queued.request('POST', '/v1/messages', json.dumps(new), headers={'Content-Type': 'application/json',
                               'Authorization': 'Bearer ' + token, 'User-Agent': 'flower-tui-sender-status/1'})
                wait_for(lambda: bool(set(SOURCE.glob('*.prepared')) - before), '排队请求未取得预留')
                receipt, = set(SOURCE.glob('*.prepared')) - before
                queued.sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, pack('ii', 1, 0))
            wait_for(lambda: receipt.stem in json.loads(ledger.read_text())['cancelled'], '账号发送器尚未记录取消')
            assert not receipt.with_suffix('.submits').exists()

        def verify_drain():
            """暂停续轮输出时，核对切换意向保留原内核。"""
            disconnect_queued_request()
            current = admin_call('GET', 'accounts/1', None)
            pending = admin_call('PUT', 'accounts/1', {'request_backend': 'native293',
                                 'request_backend_revision': current['request_backend_revision']})
            assert pending['request_backend'] == 'tui_v2' and pending['request_backend_pending'] == 'native293'
            # 取消本次意向，使后续的模型错误和缓存对照继续使用同一账号的 V2。
            selected_again = admin_call('PUT', 'accounts/1', {'request_backend': 'tui_v2',
                                        'request_backend_revision': pending['request_backend_revision']})
            assert selected_again['request_backend'] == 'tui_v2' and selected_again['request_backend_pending'] is None

        final, second_size = public_stream(token, follow, result, while_paused=verify_drain)
        assert final[-1]['type'] == 'message_stop' and final[-2]['delta']['stop_reason'] == 'end_turn'
        assert final[-2]['usage']['output_tokens'] == 3
        assert len(set(SOURCE.glob('*.submits')) - existing) == 2
        errors = {}
        fault = SOURCE / 'response-status'
        for status in (401, 403, 429):
            before = set(SOURCE.glob('*.submits'))
            fault.write_text(str(status))
            try:
                code, error = http(18090, 'POST', '/v1/messages', token, body)
                assert code == status and error['error']['message'] == f'合成错误 {status}', (status, code, error)
            finally:
                fault.unlink()
            attempted, = set(SOURCE.glob('*.submits')) - before
            assert attempted.read_text().splitlines() == ['1']
            errors[str(code)] = 1
        cache = verify_cache(token)
        set_runtime(generation, True)
        current = admin_call('GET', 'accounts/1', None)
        assert current['request_backend'] == 'tui_v2' and current['tui_v2_available'] is False
        restored = admin_call('PUT', 'accounts/1', {'request_backend': 'native293',
                              'request_backend_revision': current['request_backend_revision']})
        assert restored['request_backend'] == 'native293' and restored['request_backend_pending'] is None, restored.keys()
        set_runtime(generation, True)
        reenabled = admin_call('PUT', 'accounts/1', {'request_backend': 'tui_v2',
                               'request_backend_revision': restored['request_backend_revision']})
        assert reenabled['request_backend'] == 'tui_v2' and reenabled['request_backend_pending'] is None
        restored = admin_call('PUT', 'accounts/1', {'request_backend': 'native293',
                              'request_backend_revision': reenabled['request_backend_revision']})
        assert restored['request_backend'] == 'native293' and restored['request_backend_pending'] is None
        return {'admin_selected': selected['request_backend'], 'admin_switched_to': restored['request_backend'], 'prompt_cache': cache,
                'enabled_v2_from_sleep': True, 'returned_to_v1_from_sleep': True, 'repeated_v1_v2_switch': True,
                'active_continuation_retained_backend': True,
                'first_http': 200, 'continuation_http': 200, 'before_source_release_bytes': [first_size, second_size],
                'foreign_tool_result_http': denied, 'altered_tool_input_http': mismatch,
                'missing_original_turn_http': missing, 'wrong_generation_tool_result_http': wrong_generation,
                'rejected_prepares': 0, 'successful_turn_submits': 2,
                'error_response_submits_per_request': errors,
                'cancelled_after_public_disconnect': True, 'cancelled_request_submits': 0,
                'raw_sse_match': True, 'same_session_tool_result': True,
                'wake_generations': [binding['generation'], generation]}
    finally:
        source.terminate()
        source.wait(timeout=5)
        write_config(binding, proxy)
