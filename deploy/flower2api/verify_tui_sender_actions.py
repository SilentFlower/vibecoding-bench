#!/usr/bin/env python3
"""以受控 Unix 事件源验收真实账号发送器的预留、单次发送和取消。"""
from __future__ import annotations

import base64
import json
import os
import sys
from contextlib import closing
from hashlib import sha256
from http.client import HTTPConnection
from pathlib import Path
from socketserver import StreamRequestHandler, ThreadingUnixStreamServer
from struct import pack
from subprocess import Popen
from time import monotonic, sleep, time_ns
from uuid import UUID, uuid4

from verify_tui_prompt_cache import CASE, fixture_reply

SOURCE = Path('/fixture')
SOCKET = SOURCE / 'events.sock'
BINDING_FIELDS = ('protocol', 'nonce', 'account_id', 'environment_id', 'generation', 'release_id')
DEADLINE_SECONDS = 15


def write_source_binding(binding: dict) -> None:
    """发布合成事件源可见的身份字段。@param binding 私有编排登记。@return 无。"""
    private = SOURCE / 'binding.json'
    fresh = private.with_suffix('.tmp')
    fresh.write_text(json.dumps({k: binding[k] for k in BINDING_FIELDS if k in binding}))
    fresh.replace(private)


def wait_for(predicate, description: str) -> None:
    """等待本机发生可观察事件。@param predicate 检查函数。@param description 失败说明。@return 无。"""
    deadline = monotonic() + DEADLINE_SECONDS
    while not predicate():
        if monotonic() >= deadline:
            raise AssertionError(description)
        sleep(0.025)


def event(kind: str, **fields) -> bytes:
    """生成合成模型的 SSE 帧。@param kind 事件类型。@param fields 协议字段。@return 原始字节。"""
    data = json.dumps({'type': kind, **fields}, ensure_ascii=False, separators=(',', ':'))
    return f'event: {kind}\ndata: {data}\n\n'.encode()


def response_parts(identifier: str, model: str = 'local-test', result: str | None = None) -> tuple[bytes, bytes]:
    """生成可暂停的工具或正文事件。@param identifier 预留 ID。@param model 请求模型。
    @param result 客户端续轮的合成工具结果。@return 放行前后的响应字节。
    """
    tool = 'toolu_' + identifier
    start = event('message_start', message={'id': 'msg_' + identifier, 'type': 'message', 'role': 'assistant',
        'content': [], 'model': model, 'usage': {'input_tokens': 3, 'output_tokens': 0}})
    if result is not None:
        block = event('content_block_start', index=0, content_block={'type': 'text', 'text': ''})
        first = event('content_block_delta', index=0, delta={'type': 'text_delta', 'text': result})
        remaining = event('content_block_delta', index=0, delta={'type': 'text_delta', 'text': '已接收'})
        stop = event('content_block_stop', index=0) + event('message_delta',
            delta={'stop_reason': 'end_turn', 'stop_sequence': None}, usage={'output_tokens': 3}) + event('message_stop')
        return start + block + first, remaining + stop
    block = event('content_block_start', index=0, content_block={'type': 'tool_use', 'id': tool,
                                                               'name': 'LocalFixture', 'input': {}})
    first = event('content_block_delta', index=0, delta={'type': 'input_json_delta', 'partial_json': '{"sample":'})
    remaining = event('content_block_delta', index=0,
        delta={'type': 'input_json_delta', 'partial_json': json.dumps(identifier) + '}'})
    stop = event('content_block_stop', index=0) + event('message_delta',
        delta={'stop_reason': 'tool_use', 'stop_sequence': None}, usage={'output_tokens': 4}) + event('message_stop')
    return start + block + first, remaining + stop


class FixtureEvents(StreamRequestHandler):
    """仅响应同一隔离容器挂载内的合成事件，使用标记文件建立验收屏障。"""

    def reply(self, value: dict) -> None:
        """写入一个控制帧。@param value 测试回执。@return 无。"""
        self.wfile.write(json.dumps(value, separators=(',', ':')).encode() + b'\n')

    def handle(self) -> None:
        """处理一次探测或在同一连接中完成准备与提交。@return 无。"""
        header = json.loads(self.rfile.readline())
        expected = json.loads((SOURCE / 'binding.json').read_text())

        def proof(frame):
            assert frame['protocol'] == 1 and frame['nonce']
            reply = {**expected, 'protocol': 1, 'nonce': frame['nonce'], 'ready': True, 'idle': True}
            if CASE.is_file():
                # 缓存对照会在回环模型核对扩展字段，绑定时需声明配套输入协议。
                reply['input_policy_protocol'] = 1
            if (SOURCE / 'wrong-generation').exists():
                reply['generation'] += 1
            return reply

        reply = proof(header)
        if header['action'] in ('status', 'bind'):
            self.reply(reply)
            if header['action'] == 'status':
                return
            second = self.rfile.readline()
            if not second:
                return
            header = json.loads(second)
            reply = proof(header)
        assert header['action'] == 'prepare'
        reservation = header['reservation']
        key = str(UUID(reservation['reservation_id']))
        assert key == reservation['reservation_id']
        body = self.rfile.read(header['body_len'])
        digest = sha256(body).hexdigest()
        assert digest == header['body_sha256']
        (SOURCE / f'{key}.prepared').write_text(digest)
        request = json.loads(body)
        results = []
        for message in reversed(request['messages']):
            if message['role'] not in ('user', 'system'):
                break
            content = message['content']
            if message['role'] == 'user' and isinstance(content, list):
                results.extend(block for block in content if block['type'] == 'tool_result')
        kind = 'new'
        if results:
            result, = results
            tool_id = result['tool_use_id']
            original = json.loads((SOURCE / 'tool-owner.json').read_text())
            assert (tool_id, reservation['principal_id'], reservation['session_id']) == tuple(original)
            kind = 'continuation'
        self.reply({**reply, 'kind': kind})
        submit = self.rfile.readline()
        if not submit:
            (SOURCE / f'{key}.released').touch()
            return
        assert json.loads(submit) == {'action': 'send', 'reservation_id': key}
        with (SOURCE / f'{key}.submits').open('a') as output:
            output.write('1\n')
        if (SOURCE / f'{key}.abort').exists():
            return
        if CASE.is_file():
            fixture_reply(self, reservation, body, kind)
            return
        failure = SOURCE / 'response-status'
        if failure.exists():
            status = int(failure.read_text())
            assert status in (401, 403, 429)
            self.reply({'status': status, 'content_type': 'application/json'})
            raw = json.dumps({'type': 'error', 'error': {'message': f'合成错误 {status}'}}).encode()
            self.wfile.write(pack('!I', len(raw)) + raw + pack('!I', 0))
            return
        if kind == 'continuation' and not request['stream']:
            self.reply({'status': 200, 'content_type': 'application/json'})
            raw = json.dumps({'id': 'msg_' + key, 'type': 'message', 'role': 'assistant', 'model': request['model'],
                'content': [{'type': 'text', 'text': '回环工具结果已接收'}],
                'stop_reason': 'end_turn', 'stop_sequence': None,
                'usage': {'input_tokens': 5, 'output_tokens': 3}}, ensure_ascii=False).encode()
            self.wfile.write(pack('!I', len(raw)) + raw + pack('!I', 0))
            return
        self.reply({'status': 200, 'content_type': 'text/event-stream'})
        if kind == 'new':
            (SOURCE / 'tool-owner.json').write_text(json.dumps(['toolu_' + key, reservation['principal_id'],
                                                               reservation['session_id']]))
        first, tail = response_parts(key, request['model'], result['content'] if kind == 'continuation' else None)
        self.wfile.write(pack('!I', len(first)) + first)
        (SOURCE / f'{key}.paused').touch()
        wait_for((SOURCE / f'{key}.release').exists, '客户端尚未放行后段')
        self.wfile.write(pack('!I', len(tail)) + tail + pack('!I', 0))


def serve() -> None:
    """在专用验收目录监听本机事件协议。@return 无。"""
    assert SOURCE.is_dir() and SOURCE.stat().st_uid == os.getuid() == 1001
    os.umask(0o077)
    if SOCKET.is_socket():
        SOCKET.unlink()
    with ThreadingUnixStreamServer(str(SOCKET), FixtureEvents) as server:
        server.daemon_threads = True
        server.serve_forever()


def identity(binding: dict, seconds: float = DEADLINE_SECONDS) -> dict:
    """生成只含受信归属的测试材料。@param binding 当前 sender 绑定。@param seconds 有效时间。@return 身份头字段。"""
    return {k: binding[k] for k in ('account_id', 'environment_id', 'generation')} | {
        'principal_id': 7, 'session_id': str(uuid4()), 'reservation_id': str(uuid4()),
        'deadline_unix_ms': time_ns() // 1_000_000 + int(seconds * 1000), 'continuation_only': False}


def call(action: str, token: str, who: dict, body: bytes = b'', *, chunked: bool = False):
    """向真实账号发送器提交私有请求。@param action 动作。@param token 合成鉴权。@param who 已绑定身份。
    @param body 原始请求正文。@param chunked 使用 HTTP 分块编码。@return 调用方须关闭的连接及响应。
    """
    header = base64.b64encode(json.dumps(who, separators=(',', ':')).encode()).decode()
    client = HTTPConnection('127.0.0.1', 8091, timeout=DEADLINE_SECONDS)
    try:
        client.request('POST', '/internal/tui-v2/' + action, body=iter((body,)) if chunked else body,
                       encode_chunked=chunked, headers={
            'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json', 'x-v3-tui-reservation': header})
        return client, client.getresponse()
    except Exception:
        client.close()
        raise


def status_code(action: str, token: str, who: dict, body: bytes = b'') -> int:
    """读完单次 JSON 或空响应。@param action 动作。@param token 合成鉴权。@param who 身份。
    @param body 发送的正文。@return HTTP 状态。
    """
    client, response = call(action, token, who, body)
    with closing(client), response:
        response.read()
        return response.status


def check_actions(binding: dict, secret: str, write_config, control, proxy: str) -> dict:
    """验证默认发送器从无源、就绪、预留、提交、取消到回落。
    @param binding 合成账号绑定。@param secret 同账号鉴权。@param write_config 临时配置写入回调。
    @param control 状态查询回调。@param proxy 隔离回环地址。@return 脱敏验收结果。
    """
    body = json.dumps({'model': 'local-test', 'stream': True, 'max_tokens': 8, 'messages': [
        {'role': 'user', 'content': '仅回环验证\n\n' + uuid4().hex}]}, ensure_ascii=False, indent=2).encode()
    disabled = status_code('prepare', secret, identity(binding), body)
    assert disabled == 503, disabled
    private_auth = {action: status_code(action, 'invalid', identity(binding), body if action == 'prepare' else b'')
                    for action in ('prepare', 'send', 'cancel')}
    assert set(private_auth.values()) == {401}, private_auth
    write_source_binding(binding)
    write_config(binding, proxy, tui_v2={'max_reservations': 3})
    source = Popen([sys.executable, str(Path(__file__).resolve()), '--source'], user=1001, group=1001, extra_groups=[])
    try:
        wait_for(SOCKET.is_socket, '本机事件源未启动')
        wait_for(lambda: control()[1]['tui_v2'].get('ready') is True, '发送器未核验本机事件源')
        misbound = identity(binding)
        (SOURCE / 'wrong-generation').touch()
        try:
            assert status_code('prepare', secret, misbound, body) == 503
            assert not (SOURCE / (misbound['reservation_id'] + '.prepared')).exists()
        finally:
            (SOURCE / 'wrong-generation').unlink()
        original = identity(binding, 110)
        key = original['reservation_id']
        assert status_code('prepare', secret, {**original, 'generation': binding['generation'] + 1}, body) >= 400
        assert not (SOURCE / f'{key}.prepared').exists()
        client, prepared = call('prepare', secret, original, body)
        with closing(client), prepared:
            assert prepared.status == 204 and prepared.getheader('x-v3-tui-handoff-kind') == 'new'
        assert (SOURCE / f'{key}.prepared').read_text() == sha256(body).hexdigest()
        assert not (SOURCE / f'{key}.submits').exists()
        foreign = status_code('send', secret, {**original, 'principal_id': 8})
        assert foreign in (400, 403, 409) and not (SOURCE / f'{key}.submits').exists(), foreign
        for action in ('send', 'cancel'):
            client, invalid = call(action, secret, original, b'x', chunked=True)
            with closing(client), invalid:
                assert invalid.status == 400 and not (SOURCE / f'{key}.submits').exists()
        client, response = call('send', secret, original, chunked=True)
        try:
            assert response.status == 200 and response.getheader('Content-Type').startswith('text/event-stream')
            expected_first, expected_tail = response_parts(key)
            wait_for((SOURCE / f'{key}.paused').exists, '事件源未到达首段屏障')
            assert response.read(len(expected_first)) == expected_first
            # 确认已经提交后再取消，原流继续收尾，重复发送仍会被拒绝。
            assert status_code('cancel', secret, original) == 204
            during = status_code('send', secret, original)
            assert during in (400, 404, 409, 410), during
            (SOURCE / f'{key}.release').touch()
            assert response.read() == expected_tail
        finally:
            (SOURCE / f'{key}.release').touch()
            response.close()
            client.close()
        assert (SOURCE / f'{key}.submits').read_text().splitlines() == ['1']
        follow = {**identity(binding), 'session_id': original['session_id'], 'continuation_only': True}
        result = {'type': 'tool_result', 'tool_use_id': 'toolu_' + key, 'content': 'fixture-ok'}
        public_body = {'model': 'local-test', 'stream': False, 'max_tokens': 8,
                       'messages': [{'role': 'user', 'content': [result]}]}
        client, prep = call('prepare', secret, follow, json.dumps(public_body).encode())
        with closing(client), prep:
            assert prep.status == 204 and prep.getheader('x-v3-tui-handoff-kind') == 'continuation'
        client, reply = call('send', secret, follow)
        with closing(client), reply:
            assert reply.status == 200 and reply.getheader('Content-Type').startswith('application/json')
            assert json.loads(reply.read())['id'] == 'msg_' + follow['reservation_id']
        cancelled = identity(binding, 110)
        cancel_key = cancelled['reservation_id']
        assert status_code('prepare', secret, cancelled, body) == 204
        client, empty_chunked = call('cancel', secret, cancelled, chunked=True)
        with closing(client), empty_chunked:
            assert empty_chunked.status == 204
        assert status_code('cancel', secret, cancelled) == 204
        wait_for((SOURCE / f'{cancel_key}.released').exists, '取消后事件源仍持有预留')
        assert status_code('send', secret, cancelled) in (400, 404, 409, 410)
        assert not (SOURCE / f'{cancel_key}.submits').exists()
        late = identity(binding, 1.5)
        late_key = late['reservation_id']
        assert status_code('prepare', secret, late, body) == 204
        wait_for((SOURCE / f'{late_key}.released').exists, '预留到期后事件源仍持有连接')
        assert status_code('send', secret, late) >= 400 and not (SOURCE / f'{late_key}.submits').exists()
        admitted = [identity(binding) for _ in range(4)]
        for reservation in admitted[:3]:
            assert status_code('prepare', secret, reservation, body) == 204
        assert status_code('prepare', secret, admitted[3], body) == 429
        assert status_code('cancel', secret, admitted[0]) == 204
        assert status_code('prepare', secret, admitted[3], body) == 204
        for reservation in admitted[1:]:
            assert status_code('cancel', secret, reservation) == 204
        lost = identity(binding, 110)
        lost_key = lost['reservation_id']
        (SOURCE / f'{lost_key}.abort').touch()
        assert status_code('prepare', secret, lost, body) == 204
        assert status_code('send', secret, lost) >= 400
        assert status_code('send', secret, lost) >= 400
        assert (SOURCE / f'{lost_key}.submits').read_text().splitlines() == ['1']
        replay = SOURCE / 'replay-input.json'
        replay.write_text(json.dumps({'body': body.decode(), 'sent': original, 'cancelled': cancelled, 'lost': lost}))
        replay.chmod(0o600)
        return {'tool_continuation_json': True, 'capacity_at_limit': 429, 'capacity_after_cancel': 204,
                'mismatched_source_received_body': False, 'unconfigured_prepare': disabled, 'unauthorized': private_auth, 'prepare': 204, 'send': 200,
                'cancel': 204, 'empty_chunked_send': 200, 'empty_chunked_cancel': 204,
                'nonempty_chunked_send_and_cancel': 400, 'source_submits': 1, 'cancelled_submits': 0, 'expired_submits': 0,
                'unknown_response_submits': 1, 'foreign_owner': foreign, 'duplicate_send': during,
                'received_before_release': True, 'post_submit_cancel_preserved_stream': True, 'response_bytes': len(expected_first) + len(expected_tail)}
    finally:
        source.terminate()
        source.wait(timeout=5)
        write_config(binding, proxy)


def check_restarted(folder: Path) -> None:
    """用同账号数据卷重建进程后重放已结束预留。@param folder 单次回环数据目录。@return 无。"""
    path = folder / 'sender/sender.json'
    config = json.loads(path.read_text())
    secret = config['binding']['secret']
    fresh = path.with_suffix('.tmp')
    fresh.write_text(json.dumps({**config, 'tui_v2': {'max_reservations': 3}}))
    fresh.chmod(0o640)
    fresh.replace(path)
    with (SOURCE / 'replay-input.json').open() as f:
        replay = json.load(f)
    source = Popen([sys.executable, str(Path(__file__).resolve()), '--source'], user=1001, group=1001, extra_groups=[])

    def ready():
        try:
            with closing(HTTPConnection('127.0.0.1', 8091, timeout=2)) as client:
                client.request('GET', '/internal/status', headers={'Authorization': 'Bearer ' + secret})
                return json.loads(client.getresponse().read()).get('tui_v2', {}).get('ready') is True
        except OSError:
            return False

    try:
        wait_for(ready, '重建后事件源未就绪')
        observed = {}
        for label in ('sent', 'cancelled', 'lost'):
            who = replay[label]
            assert time_ns() // 1_000_000 < who['deadline_unix_ms'], '须在原截止内验证重放'
            counter = SOURCE / (who['reservation_id'] + '.submits')
            previous = counter.read_bytes() if counter.exists() else b''
            code = status_code('prepare', secret, who, replay['body'].encode())
            assert code in (400, 403, 409, 410), (label, code)
            assert status_code('send', secret, who) >= 400
            assert (counter.read_bytes() if counter.exists() else b'') == previous
            observed[label] = 0
        results = folder / 'results.json'
        data = json.loads(results.read_text())
        data['sender_actions']['additional_submits_after_restart'] = observed
        results.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    finally:
        source.terminate()
        source.wait(timeout=5)


if __name__ == '__main__':
    if sys.argv[1:] != ['--source']:
        raise SystemExit('请通过 verify_tui_sender_status.py 运行受控回归')
    serve()
