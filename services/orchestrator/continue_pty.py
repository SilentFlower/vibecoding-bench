"""本机与节点共用原续聊PTY启动，版本、身份和输入许可沿原作业。"""
from __future__ import annotations

import shlex

from cli_telemetry_policy import cli_telemetry_environment


def open_continue_pty(runtime, token: str, session_id: str, permission_mode: str, model: str = ''):
    """登记实际exec并在启动前再次核对原许可。

    :param runtime: 原AccountRuntime。
    :param token: 原续聊实际作业。
    :param session_id: 原Claude会话。
    :param permission_mode: 原冻结权限模式。
    :param model: 原冻结模型覆盖。
    :return: 实际exec ID与非阻塞原PTY socket。
    """
    job = runtime.job_for_container(token)
    runtime.authorize_input(job)
    cwd = job['cwd']
    command = ('if [ -f ' + shlex.quote(cwd + '/.claude.json') + ' ] && [ ! -f "$HOME/.claude.json" ]; then '
        'cp ' + shlex.quote(cwd + '/.claude.json') + ' "$HOME/.claude.json"; fi; '
        'if [ -n "${CLAUDE_MODEL_OVERRIDE:-}" ]; then '
        'claude --permission-mode "$CLAUDE_PERMISSION_MODE" --resume "$CONTINUE_SESSION_ID" --model "$CLAUDE_MODEL_OVERRIDE"; '
        'else claude --permission-mode "$CLAUDE_PERMISSION_MODE" --resume "$CONTINUE_SESSION_ID"; fi')
    arguments = ['setsid', '--wait', 'sh', '-c', f"echo $$ > /run/v3/jobs/{job['handle']}/group.pid; exec "
        + shlex.join(runtime.cli_command(['sh', '-c', command]))]
    environment = {'HOME': '/home/node', 'CLAUDE_CODE_VERSION': job['version'],
        'TERM': 'xterm-256color', 'COLUMNS': '120', 'LINES': '36',
        'PATH': f"/cli/{job['version']}/node_modules/.bin:/usr/local/bin:/usr/bin:/bin",
        'NETWORK_INSPECTION_MODE': job['network_inspection_mode'], **runtime.execution_environment(job['row']),
        'CONTINUE_SESSION_ID': session_id, 'CLAUDE_PERMISSION_MODE': permission_mode}
    if model:
        environment['CLAUDE_MODEL_OVERRIDE'] = model
    if job['network_inspection_mode'] != 'passthrough':
        environment.update(dict.fromkeys(('NODE_EXTRA_CA_CERTS', 'SSL_CERT_FILE', 'REQUESTS_CA_BUNDLE',
            'CURL_CA_BUNDLE', 'GIT_SSL_CAINFO'), '/etc/mitm/mitmproxy-ca-cert.pem'))
    api = runtime.client.api
    exec_id = api.exec_create(job['row']['container_id'], arguments, stdin=True, tty=True, user='1000',
        environment=cli_telemetry_environment(environment), workdir=cwd)['Id']
    runtime.register_exec(token, exec_id)
    runtime.authorize_input(job)
    stream = api.exec_start(exec_id, detach=False, tty=True, stream=False, socket=True, demux=False)
    raw = getattr(stream, '_sock', None) or stream
    raw.setblocking(False)
    return exec_id, raw
