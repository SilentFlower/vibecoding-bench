#!/usr/bin/env python3
"""用双官方交互终端验收单槽候选的公开 Messages 工具交接和实时响应。"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from difflib import SequenceMatcher
from gzip import decompress
from hashlib import file_digest, sha256
from http.client import HTTPConnection
import json
from os import write
from pathlib import Path
from queue import Queue
from re import sub
from select import select
import shlex
from shutil import which
from subprocess import check_output, run
import sys
from tempfile import mkdtemp
from threading import Event
from traceback import format_exc
from urllib.parse import urlsplit
from uuid import uuid4

from verify_tui_concurrency import CLEAN_ENV, ROOT, VERSION, Terminal, frame, record, wait_for, write_json
from verify_tui_http_handoff import (
    COMPETING, Endpoint, HandoffFixture, final_text, gateway_ingress, http_request,
    monitor_read, public_post, read_counts, serve,
)

SCRIPT = Path(__file__).resolve()
NOTE = 'isolated-note.txt'
ARGS = {'file_path': NOTE}
TOOL = 'mcp__relay__read_note'
WAIT = 12
OFFICIAL_CLI_SHA256 = '8968405e26db478af44eabc4635ab5ca557057b702a54460a59c13e1b253e978'
READ_MOD = """
import {endpoint, token, path, toolId} from './binding.js'

export function register(on) {
  on('tool.call', {tool: 'Read'}, async ($, call) => {
    if (call.file_path !== path || call.tool_use_id !== toolId) {
      return {deny: '只接受固定回环夹具的 Read'}
    }
    try {
      const reply = await $.http.fetch(endpoint, {
        method: 'POST', headers: {'content-type': 'application/json', authorization: 'Bearer ' + token},
        body: JSON.stringify({tool_use_id: call.tool_use_id, file_path: call.file_path}),
      })
      if (reply.ok) return {result: JSON.parse(reply.text)}
    } catch (_) {
      // 官方运行时会跳过抛错的 hook；验收要禁止继续本地 Read。
    }
    return {deny: '回环工具结果不可用'}
  })
}
"""


def text_parts(content):
    """提取 Messages 文本块。@param content 字符串或块数组。@return 文本块列表。"""
    return [content] if isinstance(content, str) else [part['text'] for part in content if part['type']=='text']


def result_block(messages):
    """取出当前用户消息的工具结果。@param messages 公开历史。@return 可选工具结果。"""
    last = messages[-1]
    assert last['role']=='user'
    content = last['content']
    blocks = [part for part in content if part['type']=='tool_result'] if isinstance(content,list) else []
    if blocks:
        block, = blocks
        return block
    return None


def read_file_bytes(result):
    """取出 Read 回包中带行号的两行文件正文。@param result Messages 工具结果。@return 文件原字节。"""
    lines = '\n'.join(text_parts(result['content'])).split('\n')
    one, sep1, first = lines[0].partition('\t')
    two, sep2, second = lines[1].partition('\t')
    assert (one,sep1,two,sep2)==('1','\t','2','\t')
    return (first+'\n'+second+'\n').encode()


def mcp(port, secret, ready_path):
    """以公开 stdio MCP 等候回传。@param port 回环端口。@param secret 合成认证。
    @param ready_path 工具列表握手证据。@return 退出码。
    """
    schema = {'type':'object','properties':{'file_path':{'type':'string'}},'required':['file_path']}
    for line in sys.stdin:
        value = json.loads(line)
        if 'id' not in value:
            continue
        method, params = value['method'], value.get('params',{})
        response = {'jsonrpc':'2.0','id':value['id']}
        if method=='initialize':
            result = {'protocolVersion':params['protocolVersion'],'capabilities':{'tools':{}},
                      'serverInfo':{'name':'relay','version':'1'}}
        elif method=='tools/list':
            result = {'tools':[{'name':'read_note','description':'Receive the client Read result.',
                                'inputSchema':schema,'annotations':{'readOnlyHint':True}}]}
        elif method=='tools/call':
            assert params['name']=='read_note' and params['arguments']==ARGS
            tool_id = params['_meta']['claudecode/toolUseId']
            status, raw = http_request(port,'POST','/fixture/mcp',secret,{'tool_use_id':tool_id})
            assert status==200
            returned = json.loads(raw)
            assert returned['tool_use_id']==tool_id
            result = {'content':returned['content']}
        elif method=='ping':
            result = {}
        else:
            print(json.dumps({**response,'error':{'code':-32601,'message':'Method not found'}}),flush=True)
            continue
        print(json.dumps({**response,'result':result}),flush=True)
        if method=='tools/list':
            ready_path.touch()
    return 0


def tool_hook(path, ask=False):
    """记录外层内置 Read 的公开 hook。@param path 证据路径。@param ask 是否要求终端确认。@return 退出码。"""
    data = json.load(sys.stdin)
    assert data['tool_name']=='Read' and Path(data['tool_input']['file_path']).name==NOTE
    details = {}
    if ask and data['hook_event_name']=='PostToolUse':
        response = data['tool_response']
        assert response['type']=='text' and response['file']['filePath']==data['tool_input']['file_path']
        details['native_result_sha256'] = input_digest(response)
    record(path,data['hook_event_name'],tool_use_id=data['tool_use_id'],session_id=data['session_id'],**details)
    if data['hook_event_name']=='PreToolUse':
        wait_for(lambda:path.with_suffix('.allow').is_file(),'验收未放行本机 Read',WAIT)
        if ask:
            print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'ask'}}))
    return 0


def input_digest(value):
    """保留字段和数组顺序计算摘要。@param value 实际 JSON 值。@return SHA-256。"""
    return sha256(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def cache_inputs(body):
    """按字段与原顺序摘要合成缓存输入。@param body 模型或公开入口实际收到的请求。@return 字段摘要。"""
    keys = ('model', 'tools', 'system', 'messages', 'cache_control', 'tool_choice', 'thinking')
    return {key: input_digest(body[key]) if key in body else None for key in keys}


def marked_prefixes(body):
    """核对每个显式断点之前的有序内容。@param body 本机合成请求。@return 断点位置及对照摘要。"""
    digest = sha256()
    marks = {}

    def add(path, value):
        digest.update(json.dumps([path, value], ensure_ascii=False, separators=(',', ':')).encode() + b'\n')
        if isinstance(value, dict) and value.get('cache_control'):
            marks[path] = digest.hexdigest()

    for i, tool in enumerate(body.get('tools', [])):
        add(f'tools[{i}]', tool)
    system = body.get('system', [])
    for i, block in enumerate(system if isinstance(system, list) else [system]):
        add(f'system[{i}]', block)
    for i, message in enumerate(body['messages']):
        add(f'messages[{i}].role', message['role'])
        content = message['content']
        for j, block in enumerate(content if isinstance(content, list) else [content]):
            add(f'messages[{i}].content[{j}]', block)
    return marks


def cache_differences(public, model, workspaces):
    """按实际结构定位差异。@param public 客户端字段。@param model 模型字段。
    @param workspaces 两侧各自的实际工作目录。@return 路径和差异类型。
    """
    differences = []
    limit = 48

    def compare(left, right, path):
        if len(differences)>=limit:
            return
        if type(left) is not type(right):
            differences.append({'path':path,'kind':'type','public':type(left).__name__,'model':type(right).__name__})
        elif isinstance(left, dict):
            if left.keys()==right.keys() and list(left)!=list(right):
                differences.append({'path':path,'kind':'key_order'})
            for key in dict.fromkeys((*left, *right)):
                if len(differences)>=limit:
                    break
                field = f'{path}.{key}'
                if key not in left or key not in right:
                    differences.append({'path':field,'kind':'missing','side':'public' if key not in left else 'model'})
                else:
                    compare(left[key],right[key],field)
        elif isinstance(left, list):
            if len(left)!=len(right):
                differences.append({'path':path,'kind':'length','public':len(left),'model':len(right)})
            for index, (a,b) in enumerate(zip(left,right)):
                compare(a,b,f'{path}[{index}]')
        elif input_digest(left)!=input_digest(right):
            difference = {'path':path,'kind':'value'}
            if isinstance(left,str):
                before, after = left.splitlines(keepends=True), right.splitlines(keepends=True)
                changes = SequenceMatcher(None,before,after).get_opcodes()
                difference['changed_line_ranges'] = [
                    {'public':[a,b],'model':[c,d],
                     'own_cwd_in_changed_lines':[any(workspaces[0] in line for line in before[a:b]),
                                                 any(workspaces[1] in line for line in after[c:d])]}
                    for kind,a,b,c,d in changes if kind!='equal'][:limit]
            differences.append(difference)

    compare(public,model,'$')
    return {'paths':differences,'limit_reached':len(differences)>=limit}


class CliFixture(HandoffFixture):
    """候选 sender 使用实际交接组件。实时事件从本次自控模拟模型发出。"""

    def __init__(self, folder, account, principal, binary, prompt, note_contents, native_read=False):
        """建立独立源。@param folder 证据。@param account 账号。@param principal 主体。
        @param binary 官方 CLI。@param prompt 多行输入。@param note_contents 客户端文件预期原字节。
        @param native_read 是否使用内置 Read 和公开 Mod。@return 无。
        """
        super().__init__(folder,account,principal)
        self.binary, self.prompt, self.note_contents = binary,prompt,note_contents
        self.secret = 'fixture-'+uuid4().hex
        self.native_read = native_read
        self.tool = 'Read' if native_read else TOOL
        self.note_path = folder.parent/'client-terminal'/'work'/NOTE
        self.arguments = {'file_path':str(self.note_path)} if native_read else ARGS
        self.inner_session = str(uuid4()) if native_read else self.turn.session_id
        if native_read:
            self.external_id = self.internal_id = 'toolu_' + uuid4().hex
        self.terminals = {}
        self.parts = {key:Queue() for key in ('original','continuation','competing')}
        self.paused = {key:Event() for key in ('original','continuation')}
        self.release = {key:Event() for key in self.paused}
        self.aborted = Event()
        self.message_ids = {key:'msg_'+uuid4().hex for key in self.parts}
        self.first = {key:'屏障_'+uuid4().hex+'\n\n' for key in self.paused}
        fence = chr(96)*3
        self.ending = {'original':'由客户端读取。\n',
                       'continuation':f'最后一行\n\n{fence}text\n你好\n{fence}',
                       'competing':'COMPETING_TURN_RAN'}
        self.tool_waiting = Event()
        self.result_ready = Event()
        self.confirmed_model = Event()
        self.forwarded = None
        self.public_cache_inputs = {}
        self.model_cache_inputs = {}
        self.public_marks = {}
        self.model_marks = {}
        self.public_cache_shapes = {}
        self.model_cache_shapes = {}

    def attach_model(self, stack):
        """监听本命名空间的模拟 Messages 和 MCP 控制端。@param stack 生命周期。@return 无。"""
        fixture = self

        class Model(Endpoint):
            """内层终端显式连接的模拟 Messages 服务。"""

            def do_POST(self):
                """按实际请求和内部调用 ID 归属模型轮。@return 无。"""
                if self.headers.get('Authorization')!='Bearer '+fixture.secret:
                    self.send_error(401)
                    return
                try:
                    raw = self.rfile.read(int(self.headers['Content-Length']))
                    data = json.loads(decompress(raw) if self.headers.get('Content-Encoding')=='gzip' else raw)
                    path = urlsplit(self.path).path
                    callback = '/fixture/read-mod' if fixture.native_read else '/fixture/mcp'
                    if path==callback:
                        expected = {'tool_use_id':fixture.internal_id}
                        if fixture.native_read:
                            expected.update(fixture.arguments)
                        with fixture.lock:
                            assert data==expected and not fixture.tool_waiting.is_set()
                            record(fixture.log,'read_mod_wait' if fixture.native_read else 'mcp_wait',
                                   tool_use_id=data['tool_use_id'])
                            fixture.tool_waiting.set()
                        assert fixture.result_ready.wait(WAIT)
                        if fixture.native_read:
                            # 固定样本的两行内容带结尾换行，Read 将空的第 3 行一并编号。
                            assert '\n'.join(text_parts(fixture.forwarded['content'])).split('\n')[2] in ('3','3\t')
                            output = {'type':'text','file':{'filePath':str(fixture.note_path),
                                'content':read_file_bytes(fixture.forwarded).decode(),
                                'numLines':3,'startLine':1,'totalLines':3}}
                            record(fixture.log,'read_mod_result',tool_use_id=data['tool_use_id'],
                                   native_result_sha256=input_digest(output))
                            self.reply(200,output)
                        else:
                            self.reply(200,fixture.forwarded)
                    elif path=='/v1/messages/count_tokens':
                        self.reply(200,{'input_tokens':24})
                    else:
                        assert path=='/v1/messages' and data['stream'] is True
                        fixture.model(self,data)
                except Exception as error:
                    record(fixture.log,'model_fixture_exception',detail=format_exc(),
                           route=urlsplit(self.path).path)
                    fixture.failure(error)
                    if not getattr(self,'stream_started',False):
                        self.send_error(400)

        self.model_port = serve(stack, Model).server_port
        if self.native_read:
            self.setup_read_mod()

    def setup_read_mod(self):
        """装配公开 Mod 和内层私有挂载。@return 无。"""
        plugin = self.folder/'read-mod'
        (plugin/'.claude-plugin').mkdir(parents=True)
        (plugin/'hooks').mkdir()
        write_json(plugin/'.claude-plugin'/'plugin.json',{'name':'fixture-native-read','version':'0.1.0'})
        write_json(plugin/'hooks'/'hooks.json',{'modules':['./read.js']})
        (plugin/'hooks'/'read.js').write_text(READ_MOD)
        binding = {'endpoint':f'http://127.0.0.1:{self.model_port}/fixture/read-mod',
                   'token':self.secret,'path':str(self.note_path),'toolId':self.internal_id}
        (plugin/'hooks'/'binding.js').write_text('\n'.join(
            f'export const {name} = {json.dumps(value)}' for name,value in binding.items())+'\n')
        mounts = ['bwrap','--die-with-parent','--unshare-pid','--unshare-ipc','--cap-drop','ALL',
                  '--ro-bind','/usr','/usr','--symlink','usr/bin','/bin','--symlink','usr/lib','/lib',
                  '--symlink','usr/lib64','/lib64','--dev','/dev','--proc','/proc','--tmpfs','/tmp',
                  '--tmpfs','/dev/shm','--ro-bind','/etc/passwd','/etc/passwd','--ro-bind','/etc/group','/etc/group',
                  '--ro-bind',str(self.binary),'/fixture/claude','--ro-bind',str(plugin),'/fixture/plugin']
        stop_hook = SCRIPT.with_name('verify_tui_concurrency.py')
        mounts.extend(('--ro-bind',str(stop_hook),str(stop_hook)))
        if not sys.executable.startswith(('/usr/','/bin/')):
            mounts.extend(('--ro-bind',sys.executable,sys.executable))
        # CLI 保留各自的真实 cwd 和 HOME。内层仅挂载自己的目录，启动前在同一命名空间核对外层路径不可见。
        preflight = 'test ! -e "$1" && test ! -d "${1%/*}" || exit 86; shift; touch ../client-path-absent; exec /fixture/claude "$@"'
        self.launcher = self.folder/'inner-cli'
        self.launcher.write_text('#!/bin/sh\nexec '+shlex.join(mounts)
            +' --bind "${PWD%/*}" "${PWD%/*}" --chdir "$PWD" -- /bin/sh -c '
            +shlex.join([preflight,'native-read',str(self.note_path)])+' "$@"\n')
        self.launcher.chmod(0o700)

    def spawn(self, session_key):
        """通过容量组件启动内层官方进程。@param session_key 私有进程键。@return 官方 Popen。"""
        label, turn = ('competing',self.new_turn) if self.processes else ('original',self.turn)
        previous = {process.pid:process.poll() for process in self.processes}
        assert all(code is not None for code in previous.values())
        if self.native_read:
            options = {'tools':'Read','extra_args':('--plugin-dir','/fixture/plugin','--permission-mode','default')}
        else:
            config = self.folder/'mcp.json'
            write_json(config,{'mcpServers':{'relay':{'command':sys.executable,
                'args':[str(SCRIPT),'--mcp',str(self.model_port),self.secret,str(self.folder/(label+'.mcp-ready'))]}}})
            options = {'extra_args':('--mcp-config',str(config),'--allowedTools',TOOL)}
        session_id = self.inner_session if label=='original' else turn.session_id
        terminal = Terminal(self.launcher if self.native_read else self.binary,self.folder/('server-'+label),session_id,
            f'http://127.0.0.1:{self.model_port}',self.secret,which('setsid'),**options)
        self.terminals[label] = terminal
        self.session_keys.append(session_key)
        self.processes.append(terminal.process)
        record(self.log,'server_terminal_started',phase=label,pid=terminal.process.pid,
               session_id=session_id,prior_exit_codes=previous)
        return terminal.process

    def parse_public(self, body):
        """校验外层真实 CLI 的 Messages。@param body 公开正文。@return 阶段和工具结果。"""
        assert body['stream'] is True
        messages = body['messages']
        result = result_block(messages)
        if result is not None:
            block, = [part for part in messages[-2]['content'] if part['type']=='tool_use']
            assert block['id']==result['tool_use_id']==self.external_id and block['name']=='Read'
            assert block['input']==self.arguments and not result.get('is_error')
            assert read_file_bytes(result)==self.note_contents
            return 'continuation',result
        prompt = text_parts(messages[-1]['content'])
        if self.prompt in prompt:
            if self.native_read:
                assert [tool['name'] for tool in body['tools']]==['Read']
            return 'original',None
        assert COMPETING in prompt, tuple(map(len,prompt))
        return 'competing',None

    def model(self, handler, body):
        """向内层终端出流，并向候选 sender 交付模拟源事件。@param handler 连接。@param body 请求。@return 无。"""
        identity = json.loads(body['metadata']['user_id'])['session_id']
        messages = body['messages']
        result = result_block(messages)
        if identity==self.inner_session:
            label = 'original'
            phase = 'continuation' if result is not None else 'original'
            names = {tool['name'] for tool in body['tools']}
            if self.native_read:
                assert names=={'Read'}
            if result is None:
                assert self.prompt in text_parts(messages[-1]['content'])
                assert self.tool in names, sorted(names)
            else:
                block, = [part for part in messages[-2]['content'] if part['type']=='tool_use']
                assert block['id']==result['tool_use_id']==self.internal_id and block['name']==self.tool
                assert block['input']==self.arguments and not result.get('is_error')
                assert read_file_bytes(result)==self.note_contents
                if self.native_read:
                    assert result==self.forwarded
        else:
            assert identity==self.new_turn.session_id and COMPETING in text_parts(messages[-1]['content'])
            label = phase = 'competing'
        pid = self.terminals[label].process.pid
        with self.lock:
            assert all(phase!=previous for _,previous,_ in self.model_activity)
            self.model_activity.append((label,phase,pid))
            if phase in ('original', 'continuation'):
                self.model_cache_inputs[phase] = cache_inputs(body)
                self.model_marks[phase] = marked_prefixes(body)
                if self.native_read:
                    self.model_cache_shapes[phase] = {key:body[key] for key in ('tools','system','messages','metadata')}
        record(self.log,'model_message_post',phase=phase,pid=pid,session_id=identity,
               tool_use_id=result['tool_use_id'] if result else None,
               read_sha256=sha256(read_file_bytes(result)).hexdigest() if result else None,
               prompt_sha256=sha256(self.prompt.encode()).hexdigest() if phase=='original' else None)
        if phase=='continuation':
            self.confirmed_model.set()
        handler.send_response(200)
        handler.send_header('Content-Type','text/event-stream')
        handler.send_header('Connection','close')
        handler.end_headers()
        handler.stream_started = handler.close_connection = True

        def emit(event, outside=None):
            encoded = frame(event)
            handler.wfile.write(encoded)
            handler.wfile.flush()
            self.parts[phase].put(encoded if outside is None else frame(outside))

        message_id = self.message_ids[phase]
        emit({'type':'message_start','message':{'id':message_id,'type':'message','role':'assistant',
            'model':body['model'],'content':[],'stop_reason':None,'stop_sequence':None,
            'usage':{'input_tokens':32,'output_tokens':1}}})
        emit({'type':'content_block_start','index':0,'content_block':{'type':'text','text':''}})
        if phase in self.paused:
            record(self.log,'source_paused',phase=phase,message_id=message_id)
            self.paused[phase].set()
            emit({'type':'content_block_delta','index':0,'delta':{'type':'text_delta','text':self.first[phase]}})
            wait_for(lambda:self.release[phase].is_set() or self.aborted.is_set(),
                     f'客户端未在源暂停期间收到正文：{phase}',WAIT)
            if self.aborted.is_set():
                record(self.log,'source_aborted',phase=phase,message_id=message_id)
                return
            record(self.log,'source_resumed',phase=phase,message_id=message_id)
        emit({'type':'content_block_delta','index':0,'delta':{'type':'text_delta','text':self.ending[phase]}})
        emit({'type':'content_block_stop','index':0})
        reason = 'end_turn'
        if phase=='original':
            external = self.handoff.offer(self.external_id,internal_id=self.internal_id,name='Read',arguments=self.arguments)
            assert external
            inside = {'type':'content_block_start','index':1,
                      'content_block':{'type':'tool_use','id':self.internal_id,'name':self.tool,'input':{}}}
            if self.native_read:
                assert inside['content_block']=={**external,'input':{}}
                emit(inside)
            else:
                emit(inside,{'type':'content_block_start','index':1,'content_block':{**external,'input':{}}})
            emit({'type':'content_block_delta','index':1,
                  'delta':{'type':'input_json_delta','partial_json':json.dumps(self.arguments)}})
            emit({'type':'content_block_stop','index':1})
            reason = 'tool_use'
        emit({'type':'message_delta','delta':{'stop_reason':reason,'stop_sequence':None},'usage':{'output_tokens':21}})
        emit({'type':'message_stop'})
        record(self.log,'source_finished',phase=phase,message_id=message_id)
        self.parts[phase].put(None)

    def dispatch(self, request, prepared, kind, result, handoff=None):
        """向原终端交付结果并逐帧返回源事件。@param request sender 连接。@param prepared 预留。
        @param kind 阶段。@param result 工具结果。@param handoff 新轮句柄。@return 无。
        """
        label = kind
        if kind=='original':
            self.handoff = handoff
            if self.native_read:
                wait_for((self.folder/'server-original'/'client-path-absent').is_file,'内层未确认客户端路径不可见',WAIT)
            else:
                wait_for((self.folder/'original.mcp-ready').is_file,'内层未完成 MCP 工具列表握手',WAIT)
            record(self.log,'accepted_public_prompt',sha256=sha256(self.prompt.encode()).hexdigest(),
                   line_count=len(self.prompt.splitlines()))
            self.terminals[kind].submit(self.prompt)
        elif kind=='continuation':
            label = 'original'
            assert self.tool_waiting.wait(WAIT) and self.store.submit(self.turn,result)
            record(self.log,'accepted_public_result',tool_use_id=result['tool_use_id'],
                   read_sha256=sha256(read_file_bytes(result)).hexdigest())

            def deliver(process, block):
                assert process is self.terminals[label].process and process.poll() is None
                self.forwarded = block if self.native_read else {
                    **block,'content':[{'type':'text','text':'\n'.join(text_parts(block['content']))}]}
                self.result_ready.set()
                assert self.confirmed_model.wait(WAIT)
                self.acknowledged += 1
                record(self.log,'original_process_confirmed',pid=process.pid,internal_id=block['tool_use_id'])
                return block['tool_use_id']

            assert self.handoff.deliver(self.external_id,internal_id=self.internal_id,send_and_ack=deliver)
            handoff = self.handoff
        else:
            self.terminals[kind].submit(COMPETING)
        request.send_response(200)
        request.send_header('Content-Type','text/event-stream')
        request.send_header('Connection','close')
        request.end_headers()
        request.close_connection = True
        while (item := self.parts[kind].get(timeout=WAIT)) is not None:
            request.wfile.write(item)
            request.wfile.flush()
        if kind!='original':
            wait_for(self.terminals[label].completed,'内层标准 Stop hook 未完成',WAIT)
            if kind=='continuation':
                self.store.close_turn(self.turn)
            self.executor.close(handoff.handle)

    def cleanup(self):
        """回收本次终端和仍等待的源。@return 无。"""
        self.aborted.set()
        for terminal in self.terminals.values():
            terminal.cleanup()


def client_edge(stack, folder, gateway, fixture):
    """用标准 HTTP 连接读取 Gateway，再转交给外层 TUI。@param stack 生命周期。@param folder 证据。
    @param gateway 公开端口。@param fixture 受控源。@return 回环端口。
    """
    ids = {value:key for key,value in fixture.message_ids.items()}

    class Client(Endpoint):
        """只以实际得到的正文增量放行模拟源。"""

        def do_POST(self):
            """将外层终端的原始请求交给真实 Gateway。@return 无。"""
            raw = self.rfile.read(int(self.headers['Content-Length']))
            headers = {key:value for key,value in self.headers.items() if key.lower() not in ('host','connection')}
            connection = HTTPConnection('127.0.0.1',gateway,timeout=WAIT+4)
            log = folder/'public.jsonl'
            try:
                if urlsplit(self.path).path == '/v1/messages':
                    body = json.loads(decompress(raw) if self.headers.get('Content-Encoding') == 'gzip' else raw)
                    phase = 'continuation' if result_block(body['messages']) else 'original'
                    with fixture.lock:
                        fixture.public_cache_inputs[phase] = cache_inputs(body)
                        fixture.public_marks[phase] = marked_prefixes(body)
                        if fixture.native_read:
                            fixture.public_cache_shapes[phase] = {key:body[key] for key in ('tools','system','messages','metadata')}
                connection.request('POST',self.path,raw,headers)
                response = connection.getresponse()
                record(log,'gateway_http_status',status=response.status,route=urlsplit(self.path).path)
                self.send_response(response.status)
                self.send_header('Content-Type',response.getheader('Content-Type','application/json'))
                self.send_header('Connection','close')
                self.end_headers()
                self.close_connection = True
                if response.status!=200 or 'text/event-stream' not in response.getheader('Content-Type',''):
                    data = response.read()
                    (folder/'gateway-error.body').write_bytes(data)
                    self.wfile.write(data)
                    return
                phase, payload = None, []
                received = bytearray()
                while line := response.readline():
                    self.wfile.write(line)
                    self.wfile.flush()
                    received.extend(line)
                    if line.startswith(b'data:'):
                        payload.append(line[5:].lstrip(b' ').rstrip(b'\r\n'))
                        continue
                    if line not in (b'\n',b'\r\n') or not payload:
                        continue
                    event = json.loads(b'\n'.join(payload))
                    payload.clear()
                    if event['type']=='message_start':
                        phase = ids[event['message']['id']]
                    record(log,'client_sse',phase=phase,frame=event)
                    delta = event.get('delta',{})
                    if phase in fixture.first and delta.get('text')==fixture.first[phase]:
                        assert fixture.paused[phase].is_set() and not fixture.release[phase].is_set()
                        record(log,'client_received_while_source_paused',phase=phase,message_id=fixture.message_ids[phase],
                               first_text=delta['text'])
                        fixture.release[phase].set()
                assert phase in fixture.first and not payload
                (folder/(phase+'.sse')).write_bytes(received)
            except Exception as error:
                fixture.failure(error)
            finally:
                connection.close()

    return serve(stack,Client).server_port


def terminal_text(folder, session_id, message_id):
    """读取终态后的官方 transcript 核对交付原字节。@param folder 终端目录。@param session_id 会话。
    @param message_id 最终响应标识。@return 助手正文。该函数不参与放行。
    """
    project = folder/'home'/'.claude'/'projects'
    path, = project.glob(f'*/{session_id}.jsonl')
    lines = (json.loads(line) for line in path.read_text().splitlines())
    rows = [row['message'] for row in lines if row.get('type')=='assistant'
            and row['message'].get('id')==message_id]
    assert rows and rows[-1]['stop_reason']=='end_turn'
    return ''.join(text for row in rows for text in text_parts(row['content']))


def read_permission_selected(path):
    """识别真实 Read 弹窗当前选中的单次批准。@param path PTY 记录。@return 当前选项是否为单次批准。"""
    # 终端可用光标位移呈现空格，匹配权限标题和选项时只忽略渲染字符。
    rendered = sub(rb'\x1b\[[0-?]*[ -/]*[@-~]',b'',path.read_bytes()).replace(b' ',b'')
    prompt = rendered.rsplit(b'Readfile',1)
    return len(prompt)==2 and b'Doyouwanttoproceed?' in prompt[-1] and '❯1.Yes'.encode() in prompt[-1]


def acceptance(root, gateway, claude, native_read=False):
    """跑单槽候选的完整工具链。@param root 证据。@param gateway 候选制品。@param claude 官方制品。
    @param native_read 是否用公开 Mod 和真实 Read 权限确认。@return 结果。
    """
    marker = 'FILE_ONLY_' + uuid4().hex
    prompt = '读取当前工作目录的隔离文件。\n\n保留两行 Unicode：花 🌸\n样本 ' + uuid4().hex
    note_contents = marker+'\n随机文件只读。\n'
    hook_log = root/'read-hook.jsonl'
    hook_command = shlex.join([sys.executable,str(SCRIPT),'--hook',str(hook_log),
                               *(['--native-read'] if native_read else [])])
    hooks = {name:[{'matcher':'Read','hooks':[{'type':'command','command':hook_command}]}]
             for name in ('PreToolUse','PostToolUse')}

    def factory(path, account, principal):
        return CliFixture(path,account,principal,claude,prompt,note_contents.encode(),native_read)

    with gateway_ingress(root/'candidate',gateway,1,True,fixture_factory=factory) as (
            port,key,admin,fixture,_), ExitStack() as stack, ThreadPoolExecutor(max_workers=1) as pool:
        outside = client_edge(stack,root,port,fixture)
        outer_path = root/'client-terminal'
        outer = Terminal(claude,outer_path,fixture.turn.session_id,f'http://127.0.0.1:{outside}',key,which('setsid'),
                         tools='Read',extra_args=('--permission-mode','default') if native_read else ('--allowedTools','Read'),
                         hooks=hooks)
        stack.callback(outer.cleanup)
        note = outer_path/'work'/NOTE
        note.write_text(note_contents)
        note.chmod(0o400)
        fd = monitor_read(stack,note)

        def gateway_counts():
            row, = admin('GET','/admin/accounts')['data']
            return row['active_requests'],row['queued_requests']

        try:
            outer.submit(prompt)
            assert fixture.tool_waiting.wait(WAIT), '内层尚未等候该工具实例'
            queued = pool.submit(public_post,fixture.folder,'competing',port,key,
                                 [{'role':'user','content':COMPETING}],fixture.new_turn.session_id)
            wait_for(lambda:fixture.capacity.snapshot().waiting==1,'新轮未等待物理名额',WAIT)
            wait_for(lambda:gateway_counts()==(0,0),'等候物理名额时普通 HTTP 槽未空闲',WAIT)
            wait_for(hook_log.is_file,'外层内置 Read 未启动',WAIT)
            assert len(fixture.processes)==1 and fixture.acknowledged==0 and not queued.done()
            assert len(fixture.model_snapshot())==1
            assert select([fd],[],[],0)[0]==[]
            record(root/'public.jsonl','queued_without_http_slot',model_posts=1,pid=fixture.processes[0].pid,
                   active_http=0,queued_http=0,actor_waiters=1,file_events_before_read=0)
            hook_log.with_suffix('.allow').touch()
            if native_read:
                terminal_raw = outer_path/'terminal.raw'
                wait_for(lambda:read_permission_selected(terminal_raw), '客户端 Read 权限弹窗未出现',WAIT)
                assert not select([fd],[],[],0)[0] and not outer.completed()
                assert fixture.acknowledged==0 and len(fixture.model_snapshot())==1
                record(root/'public.jsonl','outer_read_permission_prompt',tool_use_id=fixture.external_id,file_events_before_read=0)
                write(outer.master,b'\r')
                record(root/'public.jsonl','outer_read_permission_approved_once',tool_use_id=fixture.external_id)
            wait_for(outer.completed,'外层官方 Stop hook 未完成',WAIT)
            assert final_text(queued.result(timeout=WAIT))==fixture.ending['competing']
            wait_for(lambda:gateway_counts()==(0,0),'Gateway 槽位最终未清零',WAIT)
        finally:
            hook_log.with_suffix('.allow').touch()
            fixture.aborted.set()
        assert not fixture.fixture_errors, fixture.fixture_errors
        assert fixture.acknowledged==1 and fixture.capacity.snapshot().in_use==fixture.capacity.snapshot().waiting==0
        calls = [json.loads(line) for line in hook_log.read_text().splitlines()]
        assert [row['event'] for row in calls]==['PreToolUse','PostToolUse']
        assert all(row['tool_use_id']==fixture.external_id for row in calls)
        masks = read_counts(fd)
        assert masks==[0x20,0x01,0x10],masks
        events = [json.loads(line) for line in (root/'public.jsonl').read_text().splitlines()]
        origin = [json.loads(line) for line in fixture.log.read_text().splitlines()]
        barriers = {}
        for phase in fixture.first:
            progress = [row['frame'] for row in events if row['event']=='client_sse' and row['phase']==phase
                        and row['frame']['type']!='ping']
            expected = ['message_start','content_block_start','content_block_delta',
                        'content_block_delta','content_block_stop']
            if phase=='original':
                expected.extend(('content_block_start','content_block_delta','content_block_stop'))
                assert progress[5]['content_block']['id']==fixture.external_id
                assert progress[5]['content_block']['name']=='Read'
                assert json.loads(progress[6]['delta']['partial_json'])==fixture.arguments
            expected.extend(('message_delta','message_stop'))
            assert [event['type'] for event in progress]==expected
            assert progress[0]['message']['id']==fixture.message_ids[phase]
            assert progress[-2]['delta']['stop_reason']==('tool_use' if phase=='original' else 'end_turn')
            assert progress[-2]['usage']['output_tokens']==21
            text = ''.join(row['delta']['text'] for row in progress if row.get('delta',{}).get('type')=='text_delta')
            assert text==fixture.first[phase]+fixture.ending[phase]
            pause, resume = (next(row['ns'] for row in origin if row['event']==name and row['phase']==phase)
                             for name in ('source_paused','source_resumed'))
            observed, = [row['ns'] for row in events if row['event']=='client_received_while_source_paused'
                         and row['phase']==phase]
            assert pause < observed < resume
            barriers[phase] = {'message_id':fixture.message_ids[phase],'paused_ns':pause,
                               'client_received_ns':observed,'resumed_ns':resume,'text':text}
        final = barriers['continuation']
        for path, session_id in ((outer_path,fixture.turn.session_id),
                                 (fixture.folder/'server-original',fixture.inner_session)):
            assert terminal_text(path,session_id,final['message_id']).encode()==final['text'].encode()
        posts = fixture.model_snapshot()
        assert posts==(('original','original',fixture.processes[0].pid),
                       ('original','continuation',fixture.processes[0].pid),
                       ('competing','competing',fixture.processes[1].pid))
        assert len([row for row in events if row['event']=='gateway_http_status' and row['status']==200
                    and row['route']=='/v1/messages'])==2
        assert fixture.store.read(fixture.turn,fixture.external_id).state=='closed'
        assert outer.completed()==1
        assert set(fixture.public_cache_inputs) == set(fixture.model_cache_inputs) == {'original','continuation'}
        cache_match = {phase: {key: digest == fixture.model_cache_inputs[phase][key]
                               for key,digest in fields.items()} for phase,fields in fixture.public_cache_inputs.items()}
        # 断点之后的文本差异不能用来断言前面已经写入的缓存会失效。
        marked_match = {phase: {path: marks.get(path) == fixture.model_marks[phase].get(path)
                                for path in sorted(marks.keys() | fixture.model_marks[phase].keys())}
                        for phase, marks in fixture.public_marks.items()}
        report = {'status':'passed','cli':VERSION,'gateway_slots':1,'public_posts_from_tui':2,'barriers':barriers,
                'public_to_inner_model_cache_fields_match':cache_match,
                'explicit_cache_breakpoint_prefixes_match':marked_match,
                'native_read_hooks':calls,'kernel_file_events':masks,'model_posts':posts,
                'terminal_final_bytes_verified':['inner','outer'],'final_sha256':sha256(final['text'].encode()).hexdigest(),
                'read_sha256':sha256(note_contents.encode()).hexdigest(),'outer_stop':outer.completed(),
                'outer_tool_id':fixture.external_id,'inner_tool_id':fixture.internal_id,'handoff_confirmations':1}
        if native_read:
            mod_result, = [row for row in origin if row['event']=='read_mod_result']
            assert mod_result['native_result_sha256']==calls[-1]['native_result_sha256']
            assert fixture.turn.session_id!=fixture.inner_session
            workspaces = (str(note.parent),str(fixture.folder/'server-original'/'work'))
            report.update({'tool_mode':'native-read','model_tool_name':'Read','functional_status':'passed',
                'outer_permission':'approved_once','inner_client_path_absent':True,
                'model_tool_result_text_matches_public':True,
                'model_tool_result_block_matches_public':True,
                'cache_prefix_status':'passed' if all(all(fields.values()) for fields in cache_match.values()) else 'failed',
                'request_structure_differences':{
                    phase:{key:cache_differences(value,fixture.model_cache_shapes[phase][key],workspaces)
                           for key,value in fields.items() if input_digest(value)!=input_digest(fixture.model_cache_shapes[phase][key])}
                    for phase,fields in fixture.public_cache_shapes.items()}})
        return report


def main():
    """仅在回环命名空间运行验收。@return 退出码。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gateway',type=Path)
    parser.add_argument('--claude',type=Path)
    parser.add_argument('--isolated',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--require-cache-prefix',action='store_true',help='要求两轮公开请求与内层模型的缓存输入逐字段一致')
    parser.add_argument('--native-read',action='store_true',help='使用内置 Read、客户端逐次批准和隔离的官方工具回调')
    parser.add_argument('--mcp',nargs=3,help=argparse.SUPPRESS)
    parser.add_argument('--hook',type=Path,help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.mcp:
        return mcp(int(args.mcp[0]),args.mcp[1],Path(args.mcp[2]))
    if args.hook:
        return tool_hook(args.hook,args.native_read)
    if args.gateway is None or args.claude is None:
        parser.error('请传入 --gateway 和 --claude 的固定制品路径')
    gateway, claude = (item.resolve(strict=True) for item in (args.gateway,args.claude))
    if not args.isolated:
        return run(['unshare','--net','--','/bin/bash','-c','ip link set lo up && exec "$@"','cli-handoff',
                    sys.executable,str(SCRIPT),'--isolated','--gateway',str(gateway),'--claude',str(claude),
                    *(['--native-read'] if args.native_read else []),
                    *(['--require-cache-prefix'] if args.require_cache_prefix else [])],
                   env=CLEAN_ENV,check=False).returncode
    assert [row['ifname'] for row in json.loads(check_output(['ip','-j','link']))]==['lo']
    assert json.loads(check_output(['ip','-j','route']))==[]
    sys.path.insert(0,str(ROOT/'services/orchestrator'))
    root = Path(mkdtemp(prefix='flower2api-tui-cli-handoff-'))
    print('证据目录',root,flush=True)
    assert check_output([claude,'--version'],env={**CLEAN_ENV,'HOME':str(root)},text=True).strip()==VERSION+' (Claude Code)'
    for name, path in (('gateway',gateway),('claude',claude)):
        with path.open('rb') as binary:
            digest = file_digest(binary,'sha256').hexdigest()
        record(root/'environment.jsonl','artifact',name=name,artifact_path=str(path),sha256=digest)
        if args.native_read and name=='claude':
            assert digest==OFFICIAL_CLI_SHA256, '内置 Read 对照要求已验收的官方 Linux x64 2.1.293 二进制'
    try:
        result = acceptance(root,gateway,claude,args.native_read)
    except Exception as error:
        write_json(root/'results.json',{'status':'failed','error':repr(error)})
        raise
    if args.require_cache_prefix and not all(all(fields.values()) for fields in result['public_to_inner_model_cache_fields_match'].values()):
        write_json(root/'results.json', {**result, 'status':'failed', 'error':'内层 TUI 重建的缓存输入与公开请求不一致'})
        return 1
    write_json(root/'results.json', result)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
