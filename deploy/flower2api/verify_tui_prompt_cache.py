"""在公开 Messages 路径比较两种回复 ID 策略下受控模型收到的缓存前缀。"""
from __future__ import annotations

import json
from contextlib import closing
from hashlib import sha256
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from sqlite3 import connect
from struct import pack
from threading import Event, Thread
from time import sleep
from uuid import uuid4

SOURCE = Path('/fixture')
CASE = SOURCE / 'cache-case.json'
TOOL = 'toolu_cache_fixture'
CREATED = {'input_tokens': 13, 'output_tokens': 9, 'cache_read_input_tokens': 0, 'cache_creation_input_tokens': 4210,
           'cache_creation': {'ephemeral_5m_input_tokens': 110, 'ephemeral_1h_input_tokens': 4100}}
READ = {'input_tokens': 7, 'output_tokens': 11, 'cache_read_input_tokens': 4210, 'cache_creation_input_tokens': 0,
        'cache_creation': {'ephemeral_5m_input_tokens': 0, 'ephemeral_1h_input_tokens': 0}}


def fixture_reply(handler, reservation, body, kind):
    """以冻结的原始字节请求独立回环模型，再按当前策略回传。
    @param handler 已鉴权的本机源连接。@param reservation 归属。
    @param body 原始 Messages 字节。@param kind 新轮或续轮。@return 无。
    """
    config = json.loads(CASE.read_text())
    if kind == 'new':
        (SOURCE/'tool-owner.json').write_text(json.dumps([TOOL, reservation['principal_id'], reservation['session_id']]))
    with closing(HTTPConnection('127.0.0.1', config['port'], timeout=12)) as model:
        model.request('POST', '/v1/messages', body=body, headers={'Content-Type': 'application/json'})
        with model.getresponse() as response:
            head = {'status': response.status, 'content_type': response.getheader('Content-Type')}
            if config['mode'] == 'gateway':
                head['message_id_mode'] = 'gateway'
            handler.reply(head)
            while chunk := response.read1(4096):
                handler.wfile.write(pack('!I', len(chunk)) + chunk)
            handler.wfile.write(pack('!I', 0))


def check_prompt_cache(token: str, arms) -> dict:
    """以无状态客户端核对输出 ID、入站与模型字节、来源用量与数据库计数。
    @param token 两份数据库中同一客户端的合成令牌。@param arms 各实验的 ID 模式、网关端口与数据库。
    @return 脱敏验收数据。
    """
    from verify_tui_sender_actions import event, wait_for

    control = {'mode': 'raw'}
    observed = []
    prefixes = set()
    release = Event()
    expected = []
    raw_id = 'msg_cache_upstream_' + uuid4().hex
    policy = {'type': 'ephemeral', 'ttl': '1h'}
    prior_id = 'toolu_completed_comparison'
    history = [
        {'role': 'user', 'content': [{'type': 'text', 'text': '先核对两份样本。'}]},
        {'role': 'assistant', 'content': [
            {'type': 'text', 'text': '先进行本地比对。'},
            {'type': 'tool_use', 'id': prior_id, 'name': 'CompareFiles', 'input': {'files': ['甲', '乙']}}]},
        {'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': prior_id,
            'content': [{'type': 'text', 'text': '甲已读取。'}, {'type': 'text', 'text': '乙与甲一致。'}]}]},
        {'role': 'assistant', 'content': [{'type': 'text', 'text': '比对完成。'}]},
        {'role': 'user', 'content': [{'type': 'text', 'text': '按约定读取本地样本。',
            'cache_control': {'type': 'ephemeral', 'ttl': '5m'}}]},
    ]
    body = {'model': 'claude-sonnet-4-6', 'max_tokens': 128, 'stream': True,
            'cache_control': {'type': 'ephemeral', 'ttl': '5m'},
            'tools': [{'name': 'CompareFiles', 'description': '比对有序样本',
                       'input_schema': {'type': 'object', 'properties': {
                           'files': {'type': 'array', 'items': {'type': 'string'}}}, 'required': ['files']}},
                      {'name': 'LocalFixture', 'description': '读取样本',
                       'input_schema': {'type': 'object', 'properties': {'sample': {'type': 'string'}}},
                       'cache_control': policy}],
            'system': [{'type': 'text', 'text': '请保留比对顺序。'},
                       {'type': 'text', 'text': 'This is a stable synthetic cache prefix.\n' * 2300,
                        'cache_control': policy}],
            'messages': history}

    class Model(BaseHTTPRequestHandler):
        """对比传入字节并用同一组断点构造可核对的合成缓存用量。"""

        def log_message(self, *args):
            """省略访问日志。@param args 请求日志参数。@return 无。"""

        def do_POST(self):
            """在首个工具参数未闭合时暂停。@return 无。"""
            wire = self.rfile.read(int(self.headers['Content-Length']))
            request = json.loads(wire)
            # 核对两轮共同的显式前缀与自动缓存设置，按接收顺序计算摘要。
            prefix = json.dumps([request['cache_control'], request['tools'], request['system'],
                                 request['messages'][:len(history)]],
                                ensure_ascii=False, separators=(',', ':')).encode()
            cached = prefix in prefixes
            prefixes.add(prefix)
            observed.append((wire, sha256(prefix).hexdigest(), cached))
            usage = READ if cached else CREATED
            identity = {'id': raw_id} if control['mode'] == 'raw' else {}
            message = {**identity, 'type': 'message', 'role': 'assistant', 'model': request['model']}
            if request['stream']:
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                self.wfile.write(event('message_start', message={**message, 'content': [], 'stop_reason': None,
                                       'stop_sequence': None, 'usage': {'input_tokens': usage['input_tokens'], 'output_tokens': 0}}))
                self.wfile.write(event('content_block_start', index=0, content_block={
                    'type': 'tool_use', 'id': TOOL, 'name': 'LocalFixture', 'input': {}}))
                self.wfile.write(event('content_block_delta', index=0, delta={
                    'type': 'input_json_delta', 'partial_json': '{"sample":'}))
                self.wfile.flush()
                if not release.wait(12):
                    return
                self.wfile.write(event('content_block_delta', index=0, delta={
                    'type': 'input_json_delta', 'partial_json': '"相同输入"}'}))
                self.wfile.write(event('content_block_stop', index=0))
                self.wfile.write(event('message_delta', delta={'stop_reason': 'tool_use', 'stop_sequence': None},
                                       usage=usage) + event('message_stop'))
            else:
                data = json.dumps({**message, 'content': [{'type': 'text', 'text': '收到结果'}],
                                   'stop_reason': 'end_turn', 'stop_sequence': None, 'usage': usage}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                # 实际源已给出正常响应头，后续生成时间可以超过网关的两秒准入预算。
                self.wfile.write(data[:1])
                self.wfile.flush()
                sleep(2.5)
                self.wfile.write(data[1:])

    def post(client, token, request):
        wire = json.dumps(request, ensure_ascii=False, indent=1).encode()
        expected.append(wire)
        client.request('POST', '/v1/messages', wire, {'Authorization': 'Bearer ' + token,
                       'Content-Type': 'application/json', 'User-Agent': 'flower-tui-sender-status/1'})
        response = client.getresponse()
        assert response.status == 200, (response.status, response.read())
        return response

    def counters(database):
        with closing(connect(database)) as db:
            return db.execute('SELECT cache_read_tokens, cache_write_tokens, cache_write_5m_tokens, '
                'cache_write_1h_tokens, partial FROM usage_records WHERE account_id=1 AND '
                '(cache_read_tokens=4210 OR cache_write_tokens=4210) ORDER BY cache_read_tokens').fetchall()

    ids = []
    with ThreadingHTTPServer(('127.0.0.1', 0), Model) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for mode, port, database in arms:
                assert counters(database) == []
                prefixes.clear()
                release.clear()
                control['mode'] = mode
                CASE.write_text(json.dumps({'mode': mode, 'port': server.server_port}))
                parts = []
                with closing(HTTPConnection('127.0.0.1', port, timeout=8)) as client, post(client, token, body) as first:
                    for line in first:
                        if not line.startswith(b'data:'):
                            continue
                        frame = json.loads(line[5:])
                        if frame['type'] == 'message_start':
                            ids.append(frame['message']['id'])
                        elif frame['type'] == 'content_block_start':
                            tool = frame['content_block']
                        elif frame['type'] == 'content_block_delta':
                            parts.append(frame['delta']['partial_json'])
                            if len(parts) == 1:
                                assert parts[0] == '{"sample":' and not release.is_set()
                                release.set()
                        elif frame['type'] == 'message_delta':
                            assert frame['usage'] == CREATED and frame['delta']['stop_reason'] == 'tool_use'
                    assert frame['type'] == 'message_stop' and tool['id'] == TOOL
                tool['input'] = json.loads(''.join(parts))
                follow = {**body, 'stream': False, 'messages': [*body['messages'],
                          {'role': 'assistant', 'content': [tool]}, {'role': 'user', 'content': [
                              {'type': 'tool_result', 'tool_use_id': tool['id'], 'content': '合成结果'}]}]}
                with closing(HTTPConnection('127.0.0.1', port, timeout=8)) as client, post(client, token, follow) as second:
                    reply = json.load(second)
                    ids.append(reply['id'])
                    assert reply['usage'] == READ and reply['stop_reason'] == 'end_turn'
                rows = [(0, 4210, 110, 4100, 0), (4210, 0, 0, 0, 0)]
                wait_for(lambda: counters(database) == rows, '来源缓存用量与网关落库不一致')
        finally:
            release.set()
            server.shutdown()
            thread.join()
            CASE.unlink(missing_ok=True)
    assert ids[:2] == [raw_id, raw_id]
    assert all(isinstance(k, str) and k.startswith('msg_') for k in ids[2:])
    assert len(set(ids)) == 3 and len(ids) == 4
    assert [v[0] for v in observed] == expected and expected[:2] == expected[2:]
    assert all(out.encode() not in wire for out in ids for wire in expected)
    assert len({v[1] for v in observed}) == 1 and [v[2] for v in observed] == [False, True, False, True]
    return {'byte_identical_upstream_requests': 4, 'same_cache_prefix_sha256': observed[0][1],
            'tool_use_id_preserved': True, 'output_ids_in_upstream_requests': 0, 'unique_gateway_reply_ids': 2,
            'control': 'synthetic-prefix-comparison', 'source_usage_and_db_match': True,
            'admission_seconds': 2, 'json_tail_delay_seconds': 2.5,
            'source_cache_write_5m': 110, 'source_cache_write_1h': 4100, 'source_cache_read': 4210}
