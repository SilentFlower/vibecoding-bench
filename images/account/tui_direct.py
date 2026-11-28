"""受管 CLI 的单轮许可、账号代理隧道和有来源的增量投影。"""

import asyncio
from contextlib import suppress
from hashlib import sha256
import json
from pathlib import Path
import re
from secrets import token_urlsafe
import sys
from threading import Event
from time import time_ns
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from passthrough import ProxyConfig, RelayError, open_upstream, relay_streams
from tui_messages import ModelResponseError, encode, same_json_value


MODEL_HOST = 'api.anthropic.com'
MODEL_PATHS = (f'https://{MODEL_HOST}/v1/messages', f'https://{MODEL_HOST}/v1/messages?beta=true')


class DirectRejected(ValueError):
    """迟到或重复的许可不改变已经认领的模型结果。"""


def _proxy(url):
    target = urlsplit(url)
    if (target.scheme not in ('http', 'socks5', 'socks5h') or not target.hostname or not target.port
            or target.path or target.query or target.fragment):
        raise ValueError('账号直发缺少原上游代理')
    return ProxyConfig(target.scheme, target.hostname, target.port, unquote(target.username or ''),
                       unquote(target.password or ''))


def _cli_peer(actor, http):
    if http.client_address[0] != '127.0.0.1' or actor.process is None:
        return False
    source = f'0100007F:{http.client_address[1]:04X}'
    destination = f'0100007F:{http.server.server_port:04X}'
    try:
        rows = (line.split() for line in Path('/proc/net/tcp').read_text().splitlines()[1:])
        matches = [row[9] for row in rows if row[1:4] == [source, destination, '01']]
        if len(matches) == 1:
            expected = Path(f'socket:[{matches[0]}]')
            for descriptor in Path(f'/proc/{actor.process.pid}/fd').iterdir():
                with suppress(FileNotFoundError):
                    if descriptor.readlink() == expected:
                        return True
    except OSError:
        return False
    return False


async def _relay(http, proxy):
    async with asyncio.timeout(10):
        upstream_reader, upstream_writer = await open_upstream(proxy, MODEL_HOST, 443)
    try:
        http.send_response_only(200)
        http.end_headers()
        reader, writer = await asyncio.open_connection(sock=http.connection)
        await relay_streams(reader, writer, upstream_reader, upstream_writer, idle_timeout=120)
    finally:
        upstream_writer.close()
        with suppress(OSError):
            await upstream_writer.wait_closed()


def _frame(event):
    return b'event: ' + event['type'].encode('ascii') + b'\ndata: ' + encode(event) + b'\n\n'


def _audit(event, handle, **fields):
    reservation = handle.reservation
    record = {name: reservation[name] for name in ('account_id', 'environment_id', 'generation', 'reservation_id')}
    print(json.dumps({'event': event, **record, **fields}), file=sys.stderr, flush=True)


class DirectModel:
    """绑定一个原版进程及其独立受管回调密钥。"""

    def __init__(self, actor):
        """建立会话专属许可。@param actor 原生账号会话。@return 无。"""
        self.actor = actor
        self.bearer = token_urlsafe(32)
        self.started = Event()
        self.step = None
        self.ticket = None
        self.http_ok = False
        self.tunnel_open = False
        self.tunnel_step = None
        self.projection = None
        self.proxy = None

    def _current(self, *, sending=False):
        actor = self.actor
        step, handle = actor.step, actor.claim
        if (step is None or step.native is None or handle is None or actor.dead.is_set()
                or not actor.oauth_file or not self.started.is_set()):
            raise DirectRejected('没有本代可发送的原生步骤')
        now = time_ns() // 1_000_000
        if sending and (not handle.account_token or not handle.expires_at or handle.expires_at <= now
                        or handle.reservation['deadline_unix_ms'] <= now):
            raise DirectRejected('本轮发送许可或账号凭据已过期')
        return step, handle

    def permit(self, payload):
        """为当前主步骤认领唯一一次模型发送。@param payload 受管引擎事件。@return 回包票据。"""
        actor = self.actor
        if payload.get('url') not in MODEL_PATHS or not isinstance(payload.get('body'), str):
            raise DirectRejected('模型目标或正文不属于本步骤')
        body = json.loads(payload['body'])
        with actor.driver.lock, actor.changed:
            step, handle = self._current(sending=True)
            if step.claimed or not actor._main_request(body, handle):
                raise DirectRejected('模型输入不匹配或本步骤已取得许可')
            for key, expected in handle.direct_options.items():
                value = body.get(key)
                if key == 'output_config' and isinstance(value, dict):
                    value = {option: value[option] for option in expected if option in value}
                if not same_json_value(value, expected):
                    raise DirectRejected('原版模型请求缺少本轮核准的提供方参数')
            if (handle.kind == 'new' and actor.agent_offer is not None
                    and not actor.driver._valid_agent(actor.agent_offer, actor.identity[-1], actor.agent_messages)):
                raise DirectRejected('子代理的原工具已失效')
            self.proxy = _proxy(actor.driver.launcher.direct_proxy(handle.reservation))
            self.step, self.ticket = step, token_urlsafe(32)
            self.http_ok, self.projection = False, None
            handle.body_source = 'interactive_cli'
            step.claimed = True
            _audit('tui_direct_model_permitted', handle, step=step.native[1])
            return {'ticket': self.ticket}

    def connect(self, http):
        """仅已花费许可的原进程可以建立到账号代理的隧道。@param http 当前 CONNECT。@return 无。"""
        actor = self.actor
        http.close_connection = True
        with actor.changed:
            try:
                step, _ = self._current(sending=True)
                if (http.path != f'{MODEL_HOST}:443' or step is not self.step or not step.claimed
                        or self.tunnel_open or self.tunnel_step is step or not _cli_peer(actor, http)):
                    raise DirectRejected('直发隧道不属于原模型请求')
                proxy = self.proxy
                self.tunnel_open, self.tunnel_step = True, step
            except ValueError:
                http.send_error(403)
                return
        try:
            asyncio.run(_relay(http, proxy))
        except (OSError, RelayError, asyncio.IncompleteReadError):
            # 连接失败保留已花费的许可。CLI 的重试仍由引擎回调拒绝。
            return
        finally:
            with actor.changed:
                self.tunnel_open = False

    def response(self, payload):
        """消费同次 HTTPS 的状态回执。@param payload 引擎的状态及回包票据。@return 回执。"""
        actor = self.actor
        with actor.changed:
            step, handle = self._current()
            if self.ticket is None or payload.get('ticket') != self.ticket or step is not self.step:
                raise DirectRejected('直发 HTTP 状态不属于当前模型步骤')
            self.ticket = None
            status = payload.get('status')
            upstream = payload.get('requestId')
            request_id = upstream if isinstance(upstream, str) and re.fullmatch(r'req_[A-Za-z0-9]{1,124}', upstream) else None
            _audit('tui_direct_model_http_response', handle, status=status if type(status) is int else None,
                   upstream_request_id=request_id)
            if type(status) is int and 400 <= status < 600:
                actor.abort(ModelResponseError(status, b'', source='managed_oauth_http'))
            elif status == 200 and payload.get('streaming') is True:
                self.http_ok = True
            else:
                actor.abort(ModelResponseError(502, b'', source='local_provider_event'))
        return {}

    def _observed(self, payload):
        with self.actor.changed:
            step, handle = self._current()
            if not self.http_ok or step is not self.step or step.stopped or step.native != (payload['turn'], payload['step']):
                raise DirectRejected('事件不属于当前直发模型步骤')
            if self.projection is None:
                self.projection = _Projection(self.actor, step, handle)
            return self.projection

    def observe(self, payload, *, signed=False):
        """投影原生步骤的实际增量。@param payload 同轮内容事件。@param signed 是否为原生签名块。@return 回执。"""
        projection = self._observed(payload)
        if signed:
            projection.signed(payload['blocks'])
        else:
            projection.add(payload['chunk'])
        return {}

    def close_response(self, payload):
        """核对 CLI 的步骤结果后写入本地投影的终态。@param payload 已关联步骤结果。@return 无。"""
        self._observed(payload).finish(payload)


class _Projection:
    def __init__(self, actor, step, handle):
        self.actor, self.step, self.handle = actor, step, handle
        self.text = {}
        self.text_digest = sha256()
        self.tools = {}
        self.indices = []
        self.next_index = 0
        self.saw_thinking = False
        self.saw_signed = False
        self.stop = None

    def _emit(self, event, *, terminal=False):
        self.actor._observe(self.step, event)
        with self.actor.changed:
            if terminal:
                self.step.final = [_frame(event)]
                self.actor.changed.notify_all()
            else:
                self.actor._publish([_frame(event)])

    def _open(self):
        if not self.step.started:
            self.handle.opening_usage_placeholder = True
            self._emit({'type': 'message_start', 'message': {'id': 'msg_' + uuid4().hex, 'type': 'message',
                'role': 'assistant', 'model': self.step.native_model, 'content': [], 'stop_reason': None,
                'stop_sequence': None, 'usage': {'input_tokens': 0, 'output_tokens': 0}}})

    def _start(self, block):
        self._open()
        index = self.next_index
        self.next_index += 1
        self._emit({'type': 'content_block_start', 'index': index, 'content_block': block})
        return index

    def signed(self, blocks):
        for block in blocks:
            if (block['type'] not in ('thinking', 'redacted_thinking')
                    or not isinstance(block.get('signature' if block['type'] == 'thinking' else 'data'), str)):
                raise ValueError('直发签名块缺少原生证明')
            index = self._start(block)
            self._emit({'type': 'content_block_stop', 'index': index})
            self.saw_signed = True

    def add(self, chunk):
        kind = chunk['kind']
        if self.stop is not None:
            raise ValueError('原生直发终态后收到新的分片')
        if kind == 'stop':
            self.stop = (chunk.get('stopReason'), chunk.get('usage'))
            return
        if kind == 'thinking':
            self.saw_thinking = True
            return
        native = chunk['index']
        if type(native) is not int or native < 0:
            raise ValueError('原生直发分片索引无效')
        if kind == 'tool':
            if native in self.tools:
                raise ValueError('原生工具索引重复')
            name = chunk['name']
            plan = self.actor.cold_history
            if plan is not None:
                if plan.native_cc:
                    if not any(tool['name'] == name for tool in self.handle.tools):
                        raise ValueError('原版模型返回了未声明的客户端工具')
                else:
                    name = plan.tools[name]['name']
            index = self._start({'type': 'tool_use', 'id': chunk['id'], 'name': name, 'input': {}})
            self.tools[native] = index
            self.indices.append(index)
            return
        if kind == 'text':
            if native not in self.text:
                self.text[native] = self._start({'type': 'text', 'text': ''})
                self.indices.append(self.text[native])
            index, text = self.text[native], chunk['text']
            self.text_digest.update(text.encode())
            delta = {'type': 'text_delta', 'text': text}
        elif kind == 'input':
            index, delta = self.tools[native], {'type': 'input_json_delta', 'partial_json': chunk['json']}
        else:
            raise ValueError('未知直发增量')
        self._emit({'type': 'content_block_delta', 'index': index, 'delta': delta})

    def finish(self, result):
        reason, usage = result.get('reason'), result.get('usage')
        if (reason not in ({'tool_use'} if self.tools else {'end_turn', 'max_tokens'})
                or self.stop != (reason, usage)
                or result.get('serverTools') != 0 or (self.saw_thinking and not self.saw_signed)
                or not isinstance(usage, dict) or any(type(usage.get(key)) is not int or usage[key] < 0
                    for key in ('input_tokens', 'output_tokens'))):
            raise ModelResponseError(502, b'', source='local_provider_event')
        answer = result.get('answer')
        if not self.tools and (not isinstance(answer, str) or self.text_digest.digest() != sha256(answer.encode()).digest()):
            raise ValueError('公开文本增量与官方步骤结果不符')
        self._open()
        for index in self.indices:
            self._emit({'type': 'content_block_stop', 'index': index})
        self._emit({'type': 'message_delta', 'delta': {'stop_reason': reason, 'stop_sequence': None}, 'usage': usage})
        self._emit({'type': 'message_stop'}, terminal=True)
