"""原作业终端的有界输入与实际投递前证明核对。"""
from __future__ import annotations

from socket import SHUT_WR


KEYS = {'Enter', 'Escape', 'Up', 'Down', 'Left', 'Right', 'Tab', 'BTab', 'Space',
    'BSpace', 'Delete', 'Home', 'End', 'PPage', 'NPage'} | {
    'C-' + character for character in 'abcdefghijklmnopqrstuvwxyz'} | {'F' + str(index) for index in range(1, 13)}


def send_terminal_input(runtime, token: str, operation_id: str, text: str, keys: list[str], submit: bool,
                        *, max_bytes: int = 48000) -> None:
    """向原作业投递原样文本与受限按键，未知提交由调用者保留原意图。

    :param runtime: 持有原作业的运行时。
    :param token: 原实际执行定位。
    :param operation_id: 原输入操作，作为服务端缓冲名。
    :param text: 原样正文。
    :param keys: 原白名单按键。
    :param submit: 是否追加Enter。
    :param max_bytes: 调用入口固定的正文上限。
    :return: None；部分投递或确认失败返回结果未知。
    """
    if len(text.encode()) > max_bytes or len(keys) > 16 or any(key not in KEYS for key in keys):
        raise ValueError('终端文本或按键不符合限制')
    job = runtime.job_for_container(token)
    with runtime.environment_lock(job['row']['environment_id']):
        if job.get('heartbeat_failed') or runtime.job_for_container(token) is not job:
            raise ValueError('账号执行归属已改变')
        runtime.authorize_input(job)
        if job.get('execution_role') == 'project-review':
            container = runtime.reviews.container(job)
        else:
            container = runtime._container(job['row'])
        command = ['tmux', '-S', job['tmux_socket']]
        stream = None
        try:
            if text:
                execution = runtime.client.api.exec_create(container.id,
                    [*command, 'load-buffer', '-b', operation_id, '-'], stdin=True, tty=False)
                stream = runtime.client.api.exec_start(execution['Id'], socket=True, tty=False)
                raw = getattr(stream, '_sock', None) or stream
                raw.settimeout(5)
                raw.sendall(text.encode())
                raw.shutdown(SHUT_WR)
                while raw.recv(4096):
                    pass
                if runtime.client.api.exec_inspect(execution['Id']).get('ExitCode') != 0:
                    raise RuntimeError('终端缓冲未确认')
                # 安装、缓冲和网络等待都可能跨越截止，实际paste与Enter须分别重新核对。
                runtime.authorize_input(job)
                result = container.exec_run([*command, 'paste-buffer', '-p', '-b', operation_id, '-t', job['tmux']])
                if result.exit_code:
                    raise RuntimeError('终端文本投递未确认')
            sequence = [*keys, *(['Enter'] if submit else [])]
            if sequence:
                runtime.authorize_input(job)
                if container.exec_run([*command, 'send-keys', '-t', job['tmux'], *sequence]).exit_code:
                    raise RuntimeError('终端按键投递未确认')
        except Exception:
            raise RuntimeError('终端输入结果未知，已保留意图，禁止自动重复发送') from None
        finally:
            if stream:
                stream.close()
            if text:
                container.exec_run([*command, 'delete-buffer', '-b', operation_id])
