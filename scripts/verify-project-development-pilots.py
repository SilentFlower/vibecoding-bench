#!/usr/bin/env python3
"""在隔离 SQLite、原生交接和真实 Docker 验收下演示需求／BUG 完整周期。

开发者与最终语义评审使用明确的合成回复，需求方通过本机 HTTPS 协议替身。
本工具不调用真实模型、账号运行时或生产服务，不能据此推断模型质量与缓存收益。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from secrets import compare_digest
from urllib.request import HTTPSHandler, build_opener
from unittest.mock import patch

import docker
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'orchestrator'))
sys.path.insert(0, str(ROOT / 'deploy/v3'))

import main as service
from project_dialogue import ProjectDialogueClient, _NoRedirect
from project_iteration import ProjectIterationManager
from project_library import ProjectLibrary, safe_relative
from project_requester_settings import ProjectRequesterSettings
from project_verifier import ProjectVerifier
from test_project_development import DevelopmentStateTests
from verify_development_browser import verify_browser


class RequesterHandler(BaseHTTPRequestHandler):
    """只处理本机合成需求方请求，按实际输入阶段选择后续消息。"""

    calls: list[dict] = []

    def log_message(self, format, *args) -> None:
        """关闭包含请求细节的默认日志。@param format 格式。@param args 参数。@return None。"""

    def do_POST(self) -> None:
        """按公开任务与真实对话返回不同追问或实施动作。@return None。"""
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        assert self.path in ('/v1/chat/completions', '/updated/v1/chat/completions')
        token = 'isolated-updated-test-key' if self.path.startswith('/updated/') else 'isolated-test-token'
        assert compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token)
        context = json.loads(body['messages'][1]['content'])
        assert 'development-reference.patch' not in json.dumps(context)
        model = body['model']
        if model == 'fixture-unavailable':
            status, payload = 503, {'error': {'code': 'temporarily_unavailable'}}
            action = None
        elif model == 'gemini-3-flash-agent':
            status, payload = 402, {'error': {'code': 'insufficient_quota'}}
            action = None
        else:
            last = context['conversation'][-1]['content']
            if context['phase'] in ('implementing', 'repairing') and last.startswith('Delivered:'):
                action, message = 'verify', ''
            elif last.startswith('Plan:'):
                action, message = 'implement', 'I agree with that plan and compatibility scope. Implement it in this same workspace, add the public regression tests, and deliver the result.'
            elif 'UsageError' in last:
                action, message = 'reply', 'How will you preserve the explicit output stream, color, usage text and format_message behavior? Propose the concrete change and tests.'
            elif '_Unbound' in last:
                action, message = 'reply', 'How will the receiver actual name, positional-only arguments and duplicate receiver rejection remain correct? Propose the concrete change and tests.'
            else:
                action, message = 'reply', 'Please trace the actual implementation boundary and explain the relevant compatibility edge cases before proposing the plan.'
            status, payload = 200, {'model': model, 'choices': [{'finish_reason': 'stop', 'message': {
                'role': 'assistant', 'content': json.dumps({'action': action, 'message': message})}}],
                'usage': {'prompt_tokens': 120, 'completion_tokens': 30}}
        self.calls.append({'model': model, 'path': self.path, 'request_auth_verified': True,
            'status': status, 'action': action, 'phase': context['phase']})
        encoded = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def exercise(case: DevelopmentStateTests, slug: str, args: argparse.Namespace) -> dict:
    """在原会话完成调查、方案、错误交付及修复后的真实程序验收。

    :param case: 已隔离的真实数据库和原生驱动夹具。
    :param slug: 实际项目键。
    :param args: 已校验本地内容与证据位置。
    :return: 可公开的实际状态和用量摘要。
    """
    manager = case.scenario_manager
    case.batch = manager.create_batch(1, '完整开发周期 ' + slug, [slug])
    manager.transition(case.batch['id'], 'start')
    case.task_id = case.sql('SELECT t.id FROM project_scenario_tasks t JOIN project_scenario_instances s '
        'ON s.id=t.scenario_instance_id JOIN project_instances i ON i.id=s.instance_id WHERE i.batch_id=?', (case.batch['id'],))[0]['id']
    answers = ['The supplied reproduction requires an implementation change. I will inspect the actual source before proposing it.',
        'ClickException.show and UsageError.show independently emit the primary error and currently omit __notes__.' if slug == 'click'
        else '_Unbound.__call__ accepts the receiver only from args before delegating to the descriptor wrapper.',
        'Plan: preserve the original call/output boundaries, repair the documented behavior only in authorized implementation files, and add original-failing public tests.',
        'Delivered: the first implementation and public regression tests are ready for independent validation.',
        'Delivered: I repaired the demonstrated failure using the agreed contract and preserved all original regression controls.']
    selected_task = None
    for index, answer in enumerate(answers):
        run, config = case.launch()
        task = case.states.task(case.task_id)
        selected_task = json.loads(task['definition_json'])
        if index in (3, 4):
            candidate = args.evidence_dir / ('wrong' if index == 3 else 'references') / slug
            workspace = case.data / safe_relative(task['workspace_relative'])
            for relative in selected_task['allowed_paths']:
                source, target = candidate / relative, workspace / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        job_id = case.submit_reply(run, config, answer)
        case.release_run(run)
        case.states._mechanical_job(job_id)
        stored = case.sql('SELECT * FROM project_evaluation_jobs WHERE id=?', (job_id,))[0]
        if index < 3:
            assert stored['status'] == 'dialogue_done', stored.get('error')
            assert not case.sql("SELECT id FROM project_task_executions WHERE task_id=? AND role='review'", (case.task_id,))
        elif index == 3:
            assert stored['status'] == 'failed', stored.get('error')
            assert 'Validation feedback:' in case.states.task(case.task_id)['next_prompt']
        else:
            assert stored['status'] == 'review_ready', stored.get('error')
    batch = case.sql('SELECT * FROM project_iteration_batches WHERE id=?', (case.batch['id'],))[0]
    assert case.states._reserve_review(batch, case.sql('SELECT * FROM accounts WHERE id=1')[0], stored)
    review = case.launches[-1][0]
    package = json.loads(case.states._package_path(job_id).read_text())
    verdict = {key: package[key] for key in ('job_id', 'task_id', 'turn_no', 'response_digest', 'basis_digest')}
    references = ['candidate:' + path for path in package['candidate_files']]
    verdict.update(decision='pass', outcome=selected_task['outcomes'][0], branch_id=None, feedback_codes=[],
        criteria=[{'id': item['id'], 'status': 'satisfied', 'reason': '合成语义评审；程序事实由真实隔离验收提供。',
            'evidence': references if item.get('allow_candidate_evidence') else item.get('evidence', [])}
            for item in package['rubric']['criteria']])
    case.submit_reply(review, case.configure_run(review, review=True), json.dumps(verdict))
    case.release_run(review)
    task = case.states.task(case.task_id)
    assert task['status'] == 'passed'
    assert len(case.sql("SELECT DISTINCT session_id FROM project_task_executions WHERE task_id=? AND role='candidate'", (case.task_id,))) == 1
    assert len(case.sql('SELECT * FROM project_task_attempts WHERE task_id=?', (case.task_id,))) == 2
    case.states._mechanical_job(job_id)
    assert case.sql('SELECT visit_completed FROM project_instances WHERE id=?', (task['instance_id'],))[0]['visit_completed'] == 1
    case.states._close_finished(batch)
    result = {'project': slug, 'batch_id': task['batch_id'], 'instance_id': task['instance_id'], 'task_id': task['id'],
        'status': task['status'], 'candidate_session_count': 1, 'turns': task['turn_no'],
        'attempts': task['attempt_count'], 'completion_count': 1,
        'conversation': case.states.attempts(task['instance_id'], task['id'])['conversation'],
        'usage': case.states.usage(task['instance_id']), 'native_result': json.loads(stored['native_result_json'])}
    return result


def main() -> None:
    """运行明确标记的隔离演示，结束收口本次服务器和临时数据。

    :return: None。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--library-root', type=Path, required=True)
    parser.add_argument('--evidence-dir', type=Path, required=True)
    parser.add_argument('--browser', action='store_true')
    args = parser.parse_args()
    args.evidence_dir = args.evidence_dir.resolve()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    certificate, private_key = args.evidence_dir / 'mock.crt', args.evidence_dir / 'mock.key'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-subj', '/CN=localhost',
        '-addext', 'subjectAltName=IP:127.0.0.1', '-keyout', str(private_key), '-out', str(certificate)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    private_key.chmod(0o600)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(certificate, private_key)
    server = ThreadingHTTPServer(('127.0.0.1', 0), RequesterHandler)
    server.socket = tls.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    trusted = ssl.create_default_context(cafile=str(certificate))
    client = ProjectDialogueClient(f'https://127.0.0.1:{server.server_port}/v1', 'isolated-test-token',
        'gemini-3-flash-agent', 'deepseek-flash', opener=build_opener(_NoRedirect(), HTTPSHandler(context=trusted)))
    previous_temp = tempfile.tempdir
    tempfile.tempdir = str(args.evidence_dir)
    case = None
    try:
        DevelopmentStateTests.setUpClass()
        case = DevelopmentStateTests('test_plan_approval_then_delivery_completes_one_task')
        case.setUp()
        case.scenario_manager.transition(case.batch['id'], 'stop')
        case.scenario_manager.stop()
        case.scenario_manager = ProjectIterationManager(case.data, ProjectLibrary(args.library_root.resolve()),
            case.manager.database, case.manager.write_lock, case.manager.submit, case.manager.settings,
            case.manager.identity, case.manager.stop_run, ProjectVerifier(docker.from_env(), case.data, case.data, args.image),
            case.manager.is_executing, dialogue=client)
        case.states = case.scenario_manager.scenarios
        case.scenario_manager.plans.control = lambda run, epoch, operation: case.control(run, epoch, operation)
        results = [exercise(case, slug, args) for slug in ('click', 'cachetools')]
        (args.evidence_dir / 'complete-cycle-native.json').write_text(json.dumps({
            'real_model_calls': 0, 'requests': RequesterHandler.calls, 'pilots': results}, ensure_ascii=False, indent=2) + '\n')
        browser_result = None
        if args.browser:
            class LocalRequesterSettings(ProjectRequesterSettings):
                """只对本次本机 HTTPS 替身加入临时证书信任。"""

                @staticmethod
                def _client(value):
                    configured = ProjectRequesterSettings._client(value)
                    configured._opener = build_opener(_NoRedirect(), HTTPSHandler(context=trusted))
                    return configured

            settings_environment = {'PROJECT_REQUESTER_BASE_URL': client.base_url, 'PROJECT_REQUESTER_API_KEY': 'isolated-test-token',
                'PROJECT_REQUESTER_MODEL': client.model, 'PROJECT_REQUESTER_FALLBACK_MODEL': client.fallback_model}
            settings = LocalRequesterSettings(case.data / 'settings/project-requester.json', settings_environment)

            def check_dynamic_configuration(public):
                """通过修改后的配置继续一个真实原生会话，独立核 HTTP 路径和模型序列。"""
                current = case.scenario_manager.dialogue
                assert current.base_url == public['base_url'] and current.revision == public['revision']
                restarted = LocalRequesterSettings(settings.path, settings_environment)
                assert restarted.public() == public
                case.batch = case.scenario_manager.create_batch(1, '动态配置协议夹具', ['click'])
                case.scenario_manager.transition(case.batch['id'], 'start')
                case.task_id = case.sql('SELECT t.id FROM project_scenario_tasks t JOIN project_scenario_instances s '
                    'ON s.id=t.scenario_instance_id JOIN project_instances i ON i.id=s.instance_id WHERE i.batch_id=?', (case.batch['id'],))[0]['id']
                run, config = case.launch()
                job = case.submit_reply(run, config, 'The existing source has been inspected; I need to propose the plan next.')
                case.release_run(run)
                case.states._mechanical_job(job)
                stored = json.loads(case.sql('SELECT result_json FROM project_dialogue_jobs WHERE evaluation_job_id=?', (job,))[0]['result_json'])
                assert stored['provider_base_url'] == public['base_url']
                assert stored['configuration_revision'] == public['revision']
                assert [attempt['model'] for attempt in stored['attempts']] == public['models']
                assert stored['model'] == 'deepseek-flash'
                assert client.base_url == settings_environment['PROJECT_REQUESTER_BASE_URL']
                case.scenario_manager.transition(case.batch['id'], 'pause')
                return {'status': 'passed', 'models': public['models'], 'provider_base_url': public['base_url'],
                    'revision_persisted': True, 'old_client_preserved': True}

            application = FastAPI()
            application.include_router(service.app.router)
            application.exception_handlers.update(service.app.exception_handlers)
            application.mount('/', StaticFiles(directory=str(ROOT / 'webui'), html=True))
            with patch.multiple(service, project_iterations=case.scenario_manager,
                    project_requester_settings=settings, _AUTH_ENABLED=False):
                browser_result = asyncio.run(verify_browser(application, args.evidence_dir / 'browser', results,
                    validate_configuration=check_dynamic_configuration))
            assert case.scenario_manager.dialogue.models == client.models
        report = {'status': 'passed', 'real_model_calls': 0, 'requester': '本机HTTPS替身',
            'developer': '合成原生会话回复', 'final_review': '合成协议判定', 'program_verification': '真实隔离Docker与冻结上游回归',
            'requests': RequesterHandler.calls, 'pilots': results, 'browser': browser_result}
        (args.evidence_dir / 'complete-cycle.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'status': report['status'], 'real_model_calls': 0,
            'projects': [row['project'] for row in results], 'browser': browser_result}, ensure_ascii=False))
    finally:
        if case:
            case.scenario_manager.stop()
            case.tearDown()
            case.doCleanups()
        DevelopmentStateTests.doClassCleanups()
        tempfile.tempdir = previous_temp
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        private_key.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
