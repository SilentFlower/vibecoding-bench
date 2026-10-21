#!/usr/bin/env python3
"""仅用于隔离生命周期测试的 CLI 替身，不打入产品镜像。"""
import json
import os
import re
import select
import shlex
import socket
import subprocess
import sys
import termios
import time
import tty
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

home = Path(os.environ["HOME"])


def run_scenario_fixture(plan: dict) -> None:
    """模拟场景回答与独立评审，仅写各自HOME和原生日志，不访问模型。

    :param plan: 真实控制端生成的schema3交接配置。
    :return: None；由原driver正常收口。
    """
    review = Path('/input/package.json').is_file()
    configuration = {} if review else json.loads((home/'.synthetic-scenarios'/(plan['session_id']+'.json')).read_text())
    directory=home/'.claude/projects'/str(Path.cwd()).replace('/','-')
    directory.mkdir(parents=True,exist_ok=True)
    session=directory/(plan['session_id']+'.jsonl')
    previous=None
    if session.exists():
        for line in session.read_text().splitlines():
            previous=json.loads(line).get('uuid',previous)
    print('Synthetic task pane',flush=True)
    tty.setraw(sys.stdin.fileno())
    os.write(sys.stdout.fileno(),b'\x1b[?2004h')
    buffer=bytearray()
    pasted=False
    count=0
    while True:
        byte=os.read(sys.stdin.fileno(),1)
        if not byte:
            return
        buffer.extend(byte)
        if buffer.endswith(b'\x1b[200~'):
            del buffer[-6:]
            pasted=True
            continue
        if buffer.endswith(b'\x1b[201~'):
            del buffer[-6:]
            pasted=False
            continue
        if byte!=b'\r' or pasted:
            continue
        prompt=bytes(buffer[:-1]).decode().replace('\r\n','\n').replace('\r','\n')
        buffer.clear()
        if not prompt.strip():
            continue
        count+=1
        identity=f"{plan['session_id']}-{os.getpid()}-{count}"
        user={'type':'user','uuid':identity+'-user','parentUuid':previous,'sessionId':plan['session_id'],
            'timestamp':datetime.now(timezone.utc).isoformat(),'message':{'role':'user','content':prompt}}
        with session.open('a') as output:
            output.write(json.dumps(user)+'\n')
        previous=user['uuid']
        if review:
            package=json.loads(Path('/input/package.json').read_text())
            answer={key:package[key] for key in ('job_id','task_id','turn_no','response_digest','basis_digest')}
            disclose='NEED_CONTEXT' in package['answer'] and bool(package['allowed_branches'])
            answer.update(decision='disclose' if disclose else 'pass',outcome=None if disclose else package['outcomes'][0],
                branch_id=package['allowed_branches'][0]['id'] if disclose else None,
                criteria=[{'id':item['id'],'status':'unknown' if disclose else 'satisfied','reason':'固定合成事实对照',
                    'evidence':item.get('evidence',[])[:1]} for item in package['rubric']['criteria']],feedback_codes=[])
            text=json.dumps(answer,ensure_ascii=False)
        else:
            key=configuration['task_key']
            state_file=home/'.synthetic-scenarios'/(plan['session_id']+'-state.json')
            state=json.loads(state_file.read_text()) if state_file.exists() else {}
            if key=='Q3' and not state.get('timeout_done'):
                state['timeout_done']=True
                state_file.write_text(json.dumps(state))
                partial=Path.cwd()/'app/partial.txt'
                partial.parent.mkdir(exist_ok=True)
                partial.write_text('保留真实超时前的半成品')
                while True:
                    time.sleep(1)
            if key=='Q4':
                (Path.cwd()/'library/example.py').write_text('VALUE = 2\n')
            text='NEED_CONTEXT：请提供调用示例。' if key=='Q2' and '冻结调用材料' not in prompt else '固定公开行为正确，当前任务已回答。'
        time.sleep(configuration.get('delay_sec',0.5) if not review else 0.5)
        response={'type':'assistant','uuid':identity+'-answer','parentUuid':previous,'sessionId':plan['session_id'],
            'timestamp':datetime.now(timezone.utc).isoformat(),'message':{'role':'assistant','id':identity,'model':'offline-fixture',
                'usage':{'input_tokens':7,'output_tokens':11,'cache_read_input_tokens':0,'cache_creation_input_tokens':0},
                'stop_reason':'end_turn','content':[{'type':'text','text':text}]}}
        with session.open('a') as output:
            output.write(json.dumps(response,ensure_ascii=False)+'\n')
        previous=response['uuid']
        print('Fixture scenario response complete',flush=True)


def run_followup_fixture() -> None:
    """消费真实 tmux 按键或粘贴，写入原生形状主会话证据，不进行推理。

    :return: None；由外部 driver 结束本测试进程。
    """
    plan = json.loads(os.environ['PROJECT_PLAN_JSON']) if os.environ.get('PROJECT_PLAN_JSON') else None
    if plan and plan.get('workflow_schema')==3:
        run_scenario_fixture(plan)
        return
    config = (json.loads((home/'.synthetic-projects'/f"{plan['session_id']}.json").read_text()) if plan
        else json.loads((home / '.synthetic-followups.json').read_text()))
    if config.get('session_by_run'):
        config['session'] = os.environ['RUN_ID']
    cwd = Path.cwd()
    project = home / '.claude/projects' / str(cwd).replace('/', '-')
    project.mkdir(parents=True, exist_ok=True)
    session = project / (config['session'] + '.jsonl')
    record = cwd / '.synthetic-turns.jsonl'
    print('Synthetic task pane', flush=True)
    # TUI 与真实 CLI 一样开启括号粘贴，跨行初始输入不能被 readline 拆成多个回合。
    tty.setraw(sys.stdin.fileno())
    os.write(sys.stdout.fileno(), b'\x1b[?2004h')
    buffer = bytearray()
    pasted = False
    used_paste = False
    input_count = 0
    previous = None
    busy_until = 0
    queued_users = []
    queued_at = {}
    native_queue = config.get('queued_command', False)
    quota_started = None
    quota_sent = set()
    while True:
        for index, sample in enumerate(config.get('quota_schedule', [])):
            if quota_started is None or index in quota_sent or time.monotonic()-quota_started < sample['after']:
                continue
            # 使用正式 statusLine 入口和正常工具响应，验证真实采集链路而非直接改额度状态。
            observed = time.time()
            identity = f"{config['session']}-quota-{index}"
            response = {'type':'assistant','uuid':identity,'parentUuid':previous,
                'sessionId':config['session'],'timestamp':datetime.now(timezone.utc).isoformat(),
                'message':{'id':identity,'role':'assistant','model':'offline-fixture','stop_reason':'tool_use',
                    'content':[{'type':'tool_use','id':identity+'-tool','name':'Bash','input':{'command':'synthetic'}}]}}
            with session.open('a') as stream:
                stream.write(json.dumps(response)+'\n')
            previous = identity
            settings = json.loads(Path(os.environ.get('CLAUDE_EXECUTION_SETTINGS',str(home/'.claude/settings.json'))).read_text())
            payload = {'cwd':str(cwd),'session_id':config['session'],'transcript_path':str(session),
                'rate_limits':{key:{'used_percentage':sample[key],'resets_at':observed+delay}
                    for key,delay in (('five_hour',600),('seven_day',3600))}}
            with (cwd/'.synthetic-quota.jsonl').open('a') as stream:
                stream.write(json.dumps({'at':observed,'five_hour':sample['five_hour'],
                    'seven_day':sample['seven_day']})+'\n')
            subprocess.run(shlex.split(settings['statusLine']['command']), input=json.dumps(payload),
                text=True,capture_output=True,check=True)
            quota_sent.add(index)
        if busy_until and native_queue:
            for queued in list(queued_users):
                if time.monotonic()-queued_at[queued['uuid']] < 2:
                    continue
                # 原生 CLI 在原回合中以附件消费消息，时间可沿用入队时刻，不能伪造独立user回合。
                prompt = queued['message']['content']
                if isinstance(prompt, list):
                    prompt = '\n'.join(item['text'] for item in prompt)
                attachment = {'type':'attachment','uuid':queued['uuid']+'-attachment',
                    'parentUuid':previous,'sessionId':config['session'],'isSidechain':False,
                    'timestamp':queued['timestamp'],'attachment':{'type':'queued_command','prompt':prompt,
                        'source_uuid':queued['uuid'],'delivery_id':queued['uuid']+'-delivery',
                        'commandMode':'prompt','origin':{'kind':'human'},'humanTurn':True}}
                with session.open('a') as stream:
                    stream.write(json.dumps({'type':'queue-operation','operation':'remove',
                        'sessionId':config['session'],'content':prompt,
                        'timestamp':datetime.now(timezone.utc).isoformat()})+'\n')
                    stream.write(json.dumps(attachment)+'\n')
                previous = attachment['uuid']
                queued_users.remove(queued)
                queued_at.pop(queued['uuid'])
        if busy_until and time.monotonic() >= busy_until:
            initial_reply = {'type':'assistant','uuid':config['session']+'-initial-done','parentUuid':previous,
                'timestamp':datetime.now(timezone.utc).isoformat(),'message':{'role':'assistant',
                    'stop_reason':'end_turn','content':[{'type':'text','text':
                        'All queued extensions complete.' if native_queue else 'Initial work complete.'}]}}
            previous = initial_reply['uuid']
            events = [initial_reply]
            for queued in queued_users:
                queued.update(parentUuid=previous,timestamp=datetime.now(timezone.utc).isoformat())
                previous = queued['uuid']
                events.append(queued)
            if queued_users:
                events.append({'type':'assistant','uuid':config['session']+'-combined-done','parentUuid':previous,
                    'timestamp':datetime.now(timezone.utc).isoformat(),'message':{'role':'assistant',
                        'stop_reason':'end_turn','content':[{'type':'thinking','thinking':'Local fixture reasoning.'},
                            {'type':'text','text':'All queued extensions complete.'}]}})
                previous = events[-1]['uuid']
            with session.open('a') as stream:
                for entry in events:
                    stream.write(json.dumps(entry)+'\n')
            queued_users.clear()
            queued_at.clear()
            busy_until = 0
            print('Fixture busy queue consumed',flush=True)
        if busy_until and not select.select([sys.stdin],[],[],0.1)[0]:
            continue
        byte = os.read(sys.stdin.fileno(), 1)
        if not byte:
            return
        buffer.extend(byte)
        if buffer.endswith(b'\x1b[200~'):
            del buffer[-6:]
            pasted = True
            used_paste = True
            continue
        if buffer.endswith(b'\x1b[201~'):
            del buffer[-6:]
            pasted = False
            continue
        # Ctrl+J 是正文换行，只有 Enter/CR 才提交；不能让替身掩盖多行被提前提交的问题。
        if byte != b'\r' or pasted:
            continue
        text = bytes(buffer[:-1]).decode().replace('\r\n', '\n').replace('\r', '\n')
        buffer.clear()
        if not text.strip():
            continue
        input_count += 1
        with record.open('a') as stream:
            stream.write(json.dumps({'text': text, 'cwd': str(cwd), 'session': config['session'],
                'at':time.time(),'busy':bool(busy_until),
                'transport': 'paste' if used_paste else 'keys'}) + '\n')
        used_paste = False
        recorded = text
        if config.get('wrap_inputs'):
            recorded = f'\n\n<pasted_content id="316b-{input_count}">\n{text}\n</pasted_content id="316b-{input_count}">\n'
        if config.get('unmatched_input') and input_count == 1:
            recorded = 'Unrecognized transport: ' + recorded
        identity = f"{config['session']}-{os.getpid()}-{input_count}"
        user = {'type': 'user', 'uuid': identity+'-user', 'parentUuid': previous,
            'timestamp': datetime.now(timezone.utc).isoformat(), 'message': {'role': 'user',
            'content': recorded if input_count == 1 else [{'type': 'text', 'text': recorded}]}}
        if plan:
            match = re.search(r'^Current step: step-(\d+)\s*$',text,re.M)
            if match is None:
                raise ValueError('合成项目指令没有当前步骤')
            step = int(match[1])
            if '--session-id' in sys.argv:
                assert sys.argv[sys.argv.index('--session-id')+1]==config['session']
            else:
                assert sys.argv[sys.argv.index('--resume')+1]==config['session']
            with session.open('a') as stream:
                stream.write(json.dumps(user)+'\n')
            previous = user['uuid']
            marker = cwd/'.synthetic-timeout-once'
            if config.get('timeout_step')==step and not marker.exists():
                marker.write_text('此次合成执行保留半成品，下一执行可接续')
                (cwd/'partial-artifact.txt').write_text('half of step '+str(step))
                while True:
                    time.sleep(1)
            if config.get('delay_sec'):
                time.sleep(config['delay_sec'])
            # 仅合成 CLI 使用可信测试程序，生产镜像不会携带参考实现。
            (cwd/'fixture_behaviors.py').write_text(config['runtime'])
            actions = {name:config['actions'][name] for name in config['step_actions'][:step]}
            source = config['seed'].replace('def handle(request):','def original_handle(request):')
            implementation = '\nfrom fixture_behaviors import evaluate\nACTIONS = '+repr(actions)+'\ndef handle(request):\n    action=request.get("action","overview")\n    if action in ACTIONS:\n        return evaluate(ACTIONS[action],request,FIELDS)\n    return original_handle(request)\n\n'
            (cwd/'app.py').write_text(source.replace("if __name__ == '__main__':",implementation+"if __name__ == '__main__':"))
            with (cwd/'fixture-progress.txt').open('a') as stream:
                stream.write('step-'+str(step).zfill(2)+'\n')
            reply = {'type':'assistant','uuid':identity+'-reply','parentUuid':previous,
                'timestamp':datetime.now(timezone.utc).isoformat(),'message':{'role':'assistant','id':identity,
                    'usage':{'input_tokens':7,'output_tokens':step*11},'stop_reason':'end_turn',
                    'content':[{'type':'text','text':'Completed the current project step.'}]}}
            with session.open('a') as stream:
                stream.write(json.dumps(reply)+'\n')
            previous = reply['uuid']
            print('Fixture project step complete',flush=True)
            continue
        if config.get('busy_seconds') and not config.get('auth_failure'):
            if input_count == 1:
                with session.open('a') as stream:
                    stream.write(json.dumps(user)+'\n')
                previous = user['uuid']
                if config.get('quota_schedule'):
                    quota_started = time.monotonic()
                    (cwd/'partial-artifact.txt').write_text('保留强制中断前的合成产物')
                busy_until = time.monotonic() + config['busy_seconds']
                print('Fixture initial work busy',flush=True)
                continue
            if busy_until:
                with session.open('a') as stream:
                    stream.write(json.dumps({'type':'queue-operation','operation':'enqueue',
                        'sessionId':config['session'],'content':recorded,
                        'timestamp':datetime.now(timezone.utc).isoformat()})+'\n')
                queued_users.append(user)
                queued_at[user['uuid']] = time.monotonic()
                continue
        if config.get('wait_for_wrapup') and input_count == 1:
            with session.open('a') as stream:
                stream.write(json.dumps(user)+'\n')
            previous = user['uuid']
            print('Fixture initial work pending', flush=True)
            continue
        attachment = {'type': 'attachment', 'uuid': identity+'-context', 'parentUuid': user['uuid']}
        assistant = {'type': 'assistant', 'uuid': identity+'-reply', 'parentUuid': attachment['uuid'],
            'timestamp': datetime.now(timezone.utc).isoformat(), 'message': {'role': 'assistant',
            'stop_reason': 'end_turn', 'content': [{'type': 'thinking', 'thinking': 'Local fixture reasoning.'},
                {'type': 'text', 'text': 'Completed the requested local fixture stage.'}]}}
        if config.get('auth_failure'):
            assistant.update(isApiErrorMessage=True, error='account_on_hold')
            assistant['message'].update(model='<synthetic>', content=[{'type': 'thinking', 'thinking': 'Not a delivery.'},
                {'type': 'text', 'text': 'Your account is on hold.'}])
        # 复现原生 CLI 的异步落盘：回复可先于输入和附件写入，同一回合仍由父链相连。
        events = [assistant, user, attachment] if config.get('out_of_order') else [user, attachment, assistant]
        with session.open('a') as stream:
            for entry in events:
                stream.write(json.dumps(entry)+'\n')
        previous = assistant['uuid']
        print('Fixture stage complete', flush=True)


if "--version" in sys.argv:
    print("9.9.9 (Synthetic lifecycle fixture)")
elif sys.argv[1:] == ["auth", "status"]:
    print(json.dumps({"loggedIn": (home / ".claude" / ".credentials.json").exists(), "authMethod": "oauth"}))
elif sys.argv[1:] == ["auth", "login"]:
    (home / ".synthetic-login-environment.json").write_text(json.dumps({key: os.environ.get(key) for key in ("TZ", "LANG", "LC_ALL")}))
    control_home = home.parents[1] if home.parent.name == ".v3-login" else home
    control_file = control_home / ".synthetic-login.json"
    control = json.loads(control_file.read_text()) if control_file.exists() else {}
    print("合成 CLI 登录会话", flush=True)
    if control.get("wait_for_code"):
        endpoint = "https://claude.com/cai/oauth/authorize" if control.get("new_endpoint") else "https://claude.ai/oauth/authorize"
        link = endpoint + "?" + urlencode({"client_id": "synthetic-client", "response_type": "code",
            "redirect_uri": "https://platform.claude.com/oauth/code/callback", "scope": "user:profile user:inference",
            "code_challenge": "c" * 43, "code_challenge_method": "S256", "state": "s" * 43})
        print(link, flush=True)
        print("请输入合成授权码：", flush=True)
        # 真实 CLI 关闭回显；替身也隐藏输入，防止验证再次依赖屏幕显示授权码。
        if sys.stdin.isatty():
            attributes = termios.tcgetattr(sys.stdin.fileno())
            attributes[3] &= ~termios.ECHO
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, attributes)
        input_count = 0
        while True:
            code = sys.stdin.readline().strip()
            input_count += 1
            (control_home / ".synthetic-code-count.json").write_text(json.dumps({"count": input_count}))
            if code == "synthetic-exit":
                sys.exit(0)
            if code == "synthetic-code":
                break
            print("合成授权码不匹配", flush=True)
    (home / ".claude").mkdir(exist_ok=True)
    (home / ".claude" / ".credentials.json").write_text(json.dumps({"claudeAiOauth": {"accessToken": control.get("access_token", "synthetic"), "refreshToken": control.get("refresh_token", "synthetic-rt"),
        "expiresAt": int(time.time() * 1000) + 3600000}}))
    top = json.loads((home / ".claude.json").read_text()) if (home / ".claude.json").exists() else {}
    top["oauthAccount"] = {"accountUuid": control.get("account_uuid", "synthetic-uuid"),
        "organizationUuid": control.get("organization_uuid", "synthetic-org"), "emailAddress": control.get("email", "synthetic@example.invalid")}
    (home / ".claude.json").write_text(json.dumps(top))
    print("合成登录完成", flush=True)
    while True:
        time.sleep(1)
else:
    if os.environ.get('PROJECT_PLAN_JSON') or (home / '.synthetic-followups.json').exists():
        run_followup_fixture()
        sys.exit(0)
    if os.environ.get("SYNTHETIC_TLS_PROBE") == "1":
        with socket.create_connection(("api.anthropic.com", 443), timeout=5) as connection:
            connection.sendall(bytes.fromhex("1603030003010203"))
    tls_keys = ("NODE_EXTRA_CA_CERTS", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "GIT_SSL_CAINFO")
    (Path.cwd() / ".synthetic-invocation.json").write_text(json.dumps({"args": sys.argv[1:], "cwd": str(Path.cwd()), "home": str(home),
        "network_mode": os.environ.get("NETWORK_INSPECTION_MODE"), "tls_environment": sorted(key for key in tls_keys if os.environ.get(key)),
        "environment": {key: os.environ.get(key) for key in ("TZ", "LANG", "LC_ALL")},
        "locale": subprocess.check_output(["locale"], text=True),
        "date": subprocess.check_output(["date", "-d", "2026-10-14 12:00:00 UTC"], text=True),
        "ls": subprocess.check_output(["ls", "-l", "--time-style=locale", str(home)], text=True)}))
    print("Synthetic task pane", flush=True)
    while True:
        time.sleep(1)
