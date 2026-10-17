#!/usr/bin/env python3
"""仅用于隔离生命周期测试的 CLI 替身，不打入产品镜像。"""
import json
import os
import select
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


def run_followup_fixture() -> None:
    """消费真实 tmux 按键或粘贴，写入原生形状主会话证据，不进行推理。

    :return: None；由外部 driver 结束本测试进程。
    """
    config = json.loads((home / '.synthetic-followups.json').read_text())
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
    while True:
        if busy_until and time.monotonic() >= busy_until:
            initial_reply = {'type':'assistant','uuid':config['session']+'-initial-done','parentUuid':previous,
                'timestamp':datetime.now(timezone.utc).isoformat(),'message':{'role':'assistant',
                    'stop_reason':'end_turn','content':[{'type':'text','text':'Initial work complete.'}]}}
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
        identity = f"{config['session']}-{input_count}"
        user = {'type': 'user', 'uuid': identity+'-user', 'parentUuid': previous,
            'timestamp': datetime.now(timezone.utc).isoformat(), 'message': {'role': 'user',
            'content': recorded if input_count == 1 else [{'type': 'text', 'text': recorded}]}}
        if config.get('busy_seconds') and not config.get('auth_failure'):
            if input_count == 1:
                with session.open('a') as stream:
                    stream.write(json.dumps(user)+'\n')
                previous = user['uuid']
                busy_until = time.monotonic() + config['busy_seconds']
                print('Fixture initial work busy',flush=True)
                continue
            if busy_until:
                with session.open('a') as stream:
                    stream.write(json.dumps({'type':'queue-operation','operation':'enqueue',
                        'sessionId':config['session'],'content':recorded,
                        'timestamp':datetime.now(timezone.utc).isoformat()})+'\n')
                queued_users.append(user)
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
    if (home / '.synthetic-followups.json').exists():
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
