"""真实 Pi SDK → 固定账号工具 → tmux → 合成 Claude → 独立 Docker 验收闭环。"""
import json
import os
import threading
import time
from contextlib import ExitStack
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import main
from account_runtime import AccountRuntime
from project_library import ProjectLibrary, read_document, write_document
from project_verifier import ProjectVerifier
from projects import ProjectsService
from projects_catalog import ProjectsCatalog
from projects_pi import ProjectsPi
from projects_runtime import ProjectsTerminal
from projects_verification import ProjectsVerification
from verify_project_scenarios import create_scenario_fixture


SYNTHETIC_CLAUDE = '''#!/usr/bin/env python3
import json,os,sys,time,tty,uuid
from pathlib import Path
args=sys.argv[1:]
if '--version' in args:
    print('9.9.9');raise SystemExit(0)
sid=args[args.index('--resume')+1] if '--resume' in args else args[args.index('--session-id')+1]
native=Path.home()/'.claude/projects'/str(Path.cwd()).replace('/','-')/(sid+'.jsonl')
native.parent.mkdir(parents=True,exist_ok=True)
counter=0
second=Path('library/example.py').read_text()=='VALUE = 2\\n'
def record(role,text):
    message={'role':role,'content':[{'type':'text','text':text}]}
    if role=='assistant':
        message.update(id=uuid.uuid4().hex,model='synthetic-projects',usage={'input_tokens':3,'output_tokens':4,'cache_read_input_tokens':0,'cache_creation_input_tokens':0})
    with native.open('a') as out:
        out.write(json.dumps({'type':role,'uuid':uuid.uuid4().hex,'sessionId':sid,'message':message})+'\\n')
tty.setraw(sys.stdin.fileno());os.write(1,b'\\x1b[?2004h')
os.write(1,'请选择执行方式\\r\\n> 调查\\r\\n  实施\\r\\n'.encode())
data=b''
while True:
    value=os.read(0,1)
    if not value:break
    data+=value
    if value!=b'\\r' or (b'\\x1b[200~' in data and b'\\x1b[201~' not in data):continue
    text=data.decode().replace('\\x1b[200~','').replace('\\x1b[201~','').strip();data=b''
    if '\\x1b[B' in text:
        os.write(1,'已选择实施，等待业务需求\\r\\n'.encode());continue
    record('user',text);counter+=1
    if counter==1:
        reply=('已经调查原成果和本轮输入，方案是新增 EXTRA = 3 并保留 VALUE = 2。请确认后再修改。' if second
            else '已经调查真实源码，方案是将 VALUE 修复为 2。请确认后我再修改。')
    else:
        if second:
            assert Path('library/example.py').read_text()=='VALUE = 2\\n'
            assert Path('app/inputs/second.txt').read_text()=='第二项独立输入，不覆盖第一项成果。\\n'
            Path('library/extra.py').write_text('EXTRA = 3\\n')
        else:
            Path('library/example.py').write_text('VALUE = 2\\n')
        reply='已按确认方案实施并交付，请独立验收。'
    record('assistant',reply);os.write(1,(reply+'\\r\\n').encode())
'''


def verify_pi_projects_execution(runtime, client, account: dict, row: dict) -> None:
    """在合成账号中验证真实 Pi 连续交付、工作区复用及历史成果重验。

    :param runtime: 已完成合成登录的账号环境。
    :param client: 当前 Docker 客户端。
    :param account: 当前测试账号。
    :param row: 已登记环境。
    :return: None，任一控制、输入、验收或清理证据错误时失败。
    """
    data = runtime.data
    with ExitStack() as stack:
        paths = {'BENCH_DATA': data, 'HOST_BENCH_DATA': runtime.host_data, 'DB_PATH': data / 'pi-projects.sqlite',
            'PROFILES_DIR': data / 'profiles', 'WORKSPACES_DIR': data / 'workspaces',
            'FLOWS_DIR': data / 'flows', 'CA_DIR': data / 'ca', 'TOPICS_FILE': data / 'missing-topics.md',
            'login_manager': None, 'project_iterations': None, 'quota_guard': None}
        for key, value in paths.items():
            stack.enter_context(patch.object(main, key, value))
        main.init_db()
        current = AccountRuntime(client, data, runtime.host_data, main.get_db, runtime.fingerprint, None, main._quota_identity)
        stack.callback(current.heartbeat_pool.shutdown)
        with main.get_db() as connection:
            connection.execute('INSERT INTO accounts(id,name,profile_path,upstream_proxy_scheme,upstream_socks5_host,upstream_socks5_port) VALUES(?,?,?,?,?,?)',
                (account['id'], account['name'], str(data / 'profiles' / account['name']),
                    account['upstream_proxy_scheme'], account['upstream_socks5_host'], account['upstream_socks5_port']))
            columns = list(row)
            connection.execute('INSERT INTO account_environments(' + ','.join(columns) + ') VALUES(' + ','.join('?' for _ in columns) + ')', tuple(row.values()))
        binary = current._root(row) / 'cli/9.9.9/node_modules/.bin/claude'
        binary.write_text(SYNTHETIC_CLAUDE); binary.chmod(0o755)
        python = current._container(row).exec_run(['python3', '-c', 'import platform;print(platform.python_version())']).output.decode().strip()
        source = data / 'pi-content'
        create_scenario_fixture(source, python)
        document = read_document(source / 'projects/fixture-one/project.json')
        task = document['scenarios'][0]['tasks'][-1]
        task.update(requires=[], development_cycle='feature', owner_materials=[])
        task['evaluation']['semantic'] = False
        document.update(schema=3)
        document['scenarios'][0]['tasks'] = [task]
        document['scenarios'][0]['entries'] = [{'id': 'default', 'task_ids': [task['id']]}]
        second = deepcopy(task)
        second.update(id='Q5', goal='在保留第一项成果的前提下交付新增模块',
            prompt='阅读第二项输入，为当前项目新增 EXTRA = 3，调查、确认方案后实施并请求独立验收。',
            requires=[{'task_id': task['id'], 'artifact': 'code'}], allowed_paths=['library/extra.py'],
            setup=[{'source': 'materials/second.txt', 'target': 'app/inputs/second.txt'}])
        second['evaluation']['native'] = 'verification/second.native.json'
        (source / 'projects/fixture-one/materials').mkdir()
        (source / 'projects/fixture-one/materials/second.txt').write_text('第二项独立输入，不覆盖第一项成果。\n')
        (source / 'projects/fixture-one/verification/second.py').write_text(
            'import json,extra\nprint(json.dumps({"extra":extra.EXTRA}))\n')
        write_document(source / 'projects/fixture-one/verification/second.native.json', {
            'script': 'verification/second.py', 'args': [], 'python_paths': ['library'],
            'expected': {'extra': 3}, 'resource_profile': 'business'})
        document['scenarios'].append({'id': 'S2', 'title': '累计交付', 'goal': second['goal'],
            'default_entry': 'default', 'entries': [{'id': 'default', 'task_ids': [second['id']]}], 'tasks': [second]})
        write_document(source / 'projects/fixture-one/project.json', document)
        write_document(source / 'catalog.json', {'schema': 3, 'version': 'pi-local-verification', 'projects': ['fixture-one']})
        library = ProjectLibrary(source).install(data)
        catalog = ProjectsCatalog(data / 'research', library)
        terminal = ProjectsTerminal(current, catalog,
            lambda: {'claude_code_version': '9.9.9', 'claude_effort_level': 'high', 'execution_model': None}, lambda *_: {})
        calls = []

        class Provider(BaseHTTPRequestHandler):
            """确定性本地模型上游，真实 Pi SDK 负责解释及执行每个工具调用。"""

            def log_message(self, *_):
                """不记录请求和测试认证头。:return: None。"""

            def do_POST(self):
                """依实际工具回执生成下一步调用。:return: None。"""
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                index = len(calls)
                last = next((json.loads(item['content']) for item in reversed(request['messages']) if item['role'] == 'tool'), {})
                operations = [
                    ('account_state', {}), ('project_read', {'project_key': 'fixture-one'}),
                    ('claude_start', {'project_key': 'fixture-one', 'objective_id': 'Q4'}),
                    ('claude_observe', {'wait_sec': 2}),
                    ('claude_input', {'keys': ['Down', 'Enter'], 'submit': False}),
                    ('claude_observe', {'wait_sec': 2}),
                    ('claude_input', {'text': '调查源码并给出将 VALUE 修复为 2 的方案。\n请等待确认后实施。'}),
                    ('claude_observe', {'wait_sec': 2}),
                    ('claude_input', {'text': '同意方案，请实施并完成验证。'}),
                    ('claude_observe', {'wait_sec': 2}), ('project_submit', {'summary': '请求独立程序验收真实交付'}),
                    ('account_state', {}),
                    ('claude_start', {'project_key': 'fixture-one', 'objective_id': 'Q5'}),
                    ('claude_observe', {'wait_sec': 2}),
                    ('claude_input', {'keys': ['Down', 'Enter'], 'submit': False}),
                    ('claude_observe', {'wait_sec': 2}),
                    ('claude_input', {'text': '调查第二项输入和已验收成果，给出新增 EXTRA = 3 的方案并等待确认。'}),
                    ('claude_observe', {'wait_sec': 2}),
                    ('claude_input', {'text': '同意方案，请实施并保留此前 VALUE = 2 的行为。'}),
                    ('claude_observe', {'wait_sec': 2}), ('project_submit', {'summary': '验收第二项交付并重验此前成果'}),
                ]
                if index < len(operations):
                    name, args = operations[index]
                    if name == 'claude_input': args['observation_id'] = last.get('observation_id', '')
                    delta = {'role': 'assistant', 'tool_calls': [{'index': 0, 'id': 'action-' + str(index),
                        'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}}]}
                else:
                    name, delta = 'complete', {'role': 'assistant', 'content': '新架构工程闭环已经过独立验收。'}
                calls.append({'name': name, 'previous_result': last})
                self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.end_headers()
                for value in ({'delta': delta, 'finish_reason': None},
                        {'delta': {}, 'finish_reason': 'stop' if name == 'complete' else 'tool_calls'}):
                    payload = {'id': 'local-' + str(index), 'object': 'chat.completion.chunk', 'model': 'fixture-pi',
                        'created': 1, 'choices': [{'index': 0, **value}]}
                    self.wfile.write(('data: ' + json.dumps(payload, ensure_ascii=False) + '\n\n').encode())
                self.wfile.write(b'data: [DONE]\n\n')

        server = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
        provider_thread = threading.Thread(target=server.serve_forever, daemon=True); provider_thread.start()
        stack.callback(server.server_close); stack.callback(server.shutdown)
        provider = lambda: {'base_url': 'http://127.0.0.1:' + str(server.server_port) + '/v1',
            'api_key': 'isolated-fixture-only', 'models': ['fixture-pi']}
        pi = ProjectsPi()
        verifier = ProjectsVerification(catalog, terminal, ProjectVerifier(client, data, runtime.host_data, current.image), pi, provider)
        service = ProjectsService(data, main.get_db, main._db_lock, catalog, terminal,
            main._projects_account,
            lambda *_: {'allowed': True}, provider, verifier, pi)
        verifier.accepted = service.accepted_work
        stack.callback(service.close)
        service.configure(1, ['fixture-one'], budget_sec=120)
        service.start(1)
        deadline = time.monotonic() + 120
        while service.controllers and time.monotonic() < deadline:
            time.sleep(0.2)
        state = service.state(1)['agents'][0]
        write_document(Path('/verify/pi-projects-result.json'), {'state': state, 'calls': calls})
        assert state['work'] and state['work']['status'] == 'passed', {'state': state, 'calls': calls}
        assert len(state['passed']) == 2
        assert len(calls) == 22, calls
        assert calls[-1]['previous_result']['status'] == 'passed'
        initial = calls[1]['previous_result']['agents'][0]
        assert [item['objective_id'] for item in initial['available_objectives']] == ['Q4'], initial
        assert [item['objective_id'] for item in initial['waiting_objectives']] == ['Q5'], initial
        after_first = calls[12]['previous_result']['agents'][0]
        assert [item['objective_id'] for item in after_first['available_objectives']] == ['Q5'], after_first
        assert after_first['waiting_objectives'] == [], after_first
        with main.get_db() as connection:
            submission = connection.execute('SELECT s.id FROM projects_submissions s JOIN projects_work w ON w.id=s.work_id '
                'WHERE w.objective_id=? AND s.status=?', ('Q5', 'passed')).fetchone()
        program = read_document(data / 'projects/submissions' / submission['id'] / 'program.json')
        assert len(program['previous_objectives']) == 1, program
        assert program['previous_objectives'][0]['objective_id'] == 'Q4'
        assert program['previous_objectives'][0]['report']['status'] == 'passed'
        workspaces = list((current._root(row) / 'projects').glob('workspace-*'))
        assert len(workspaces) == 1, workspaces
        assert (workspaces[0] / 'library/example.py').read_text() == 'VALUE = 2\n'
        assert (workspaces[0] / 'library/extra.py').read_text() == 'EXTRA = 3\n'
        events = service.events(1)
        assert len([item for item in events if item['kind'] == 'input']) == 6
        assert len(current.jobs) == 0
        assert state['claude_usage']['output_tokens'] == 16, state['claude_usage']
        print(json.dumps({'pi_projects': 'passed', 'real_model_calls': 0, 'tool_calls': 21,
            'native_tty_inputs': 6, 'independent_docker_verification': 'passed',
            'dependent_objectives': 2, 'shared_workspace': True, 'previous_objectives_reverified': 1}, ensure_ascii=False))
