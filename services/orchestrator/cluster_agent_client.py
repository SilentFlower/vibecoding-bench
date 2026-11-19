"""控制容器内的固定私有节点客户端，通过原长驻服务保留实际jobs。"""
from __future__ import annotations

import json
import os
import re
import socket
import sys
from http.client import HTTPConnection
from pathlib import Path

from cluster_draft_login_operations import DRAFT_LOGIN_OPERATIONS, DRAFT_LOGIN_SHORT_OPERATIONS
from cluster_owner_operations import OWNER_OPERATIONS
from cluster_environment_operations import ENVIRONMENT_OPERATIONS, response_limit
from system_update_contract import strict_json


class _NodeConnection(HTTPConnection):
    """固定UDS连接，建连失败也立即关闭实际文件描述符。"""

    def __init__(self, path: Path, timeout: float | None) -> None:
        """固定原socket及有界读写期限。:param path: 本容器UDS。:param timeout: 读写秒数。:return: None。"""
        super().__init__('node.internal', timeout=timeout)
        self.path = path

    def connect(self) -> None:
        """建立同容器UDS，失败保持原操作未知且释放socket。:return: None。"""
        stream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            stream.settimeout(2)
            stream.connect(str(self.path))
            stream.settimeout(self.timeout)
        except BaseException:
            stream.close()
            raise
        self.sock = stream


def node_agent_request(data: Path, token: str, operation: str, raw: bytes) -> dict:
    """向本容器的私有UDS提交一次固定动作，未知提交由原调用方核对。

    :param data: 精确安装数据根。
    :param token: 本节点独立服务认证。
    :param operation: 固定节点操作。
    :param raw: 有界JSON输入。
    :return: 有界私有协议回执。
    """
    allowed = {'health', 'prepare', 'inspect', 'account-quiesce', 'review-admission', 'fence', 'export', 'stage-import', 'verify-import',
        'prepare-import', 'activate-import', 'restore-source', 'revoke-import', 'restart-preserved', 'stage-preparation-files', 'prepare-files',
        'grant-create', 'grant-renew', 'grant-get', 'grant-close', 'credential-refresh-start', 'credential-refresh-get', 'credential-status', 'credential-material', 'credential-identity', 'credential-usage-get', 'account-login-get', 'account-login-observe', 'account-login-code-receipt', 'account-login-snapshot', 'account-login-input', 'account-bound-identity', 'account-bound-login-start', 'account-bound-login-get', 'account-bound-login-stop', 'account-bound-login-observe', 'account-bound-login-code', 'account-bound-login-code-receipt', 'account-bound-login-commit', 'account-bound-login-snapshot', 'account-bound-login-accept', 'account-bound-login-discard', 'account-bound-login-input', 'account-bound-login-publish', 'account-bound-login-abort', 'credential-refresh-stop', 'account-login-start', 'account-login-stop', 'account-login-code', 'account-login-commit', 'account-login-accept', 'account-login-discard', 'credential-usage-start', 'credential-usage-stop', 'terminal-assets', 'terminal-start',
        'terminal-get', 'terminal-observe', 'terminal-send', 'terminal-input', 'terminal-control',
        'terminal-conversation', 'terminal-usage', 'terminal-passive', 'terminal-passive-ack', 'terminal-quota-state', 'terminal-quota-read', 'api-quota-read', 'project-history-capture', 'terminal-capture', 'terminal-maintenance', 'terminal-recover', 'terminal-reconcile', 'terminal-snapshot', 'terminal-snapshot-get', 'terminal-verification-start', 'terminal-verification-get', 'terminal-verification-cancel', 'run-verification-start', 'run-verification-get', 'run-verification-cancel', 'run-review-input-stage', 'run-review-input-commit', 'run-review-input-facts', 'run-scenario-input-stage', 'run-scenario-input-commit', 'run-scenario-input-facts', 'run-scenario-input-archive', 'run-project-prepare', 'run-project-configure', 'run-project-decision', 'run-project-facts', 'run-project-native', 'run-project-permit', 'run-snapshot', 'run-snapshot-get', 'run-start', 'run-get', 'run-poll', 'run-control', 'run-recover', 'run-quota-state', 'run-quota-read', 'run-artifact', 'run-files', 'run-file', 'run-stats', 'run-capture', 'run-session', 'run-refresh', 'run-refresh-get', 'run-owner-refresh-defer', 'continue-start', 'continue-get', 'continue-input', 'continue-control', 'continue-recover', 'continue-quota-state', 'continue-quota-read', 'continue-quota-control', 'continue-credentials'}
    allowed.update(DRAFT_LOGIN_OPERATIONS)
    allowed.update(OWNER_OPERATIONS)
    allowed.update(ENVIRONMENT_OPERATIONS)
    if operation not in allowed or not re.fullmatch('[a-f0-9]{64}', token) or len(raw) > 2 * 1024 * 1024:
        raise ValueError('节点私有操作或认证格式无效')
    timeout = 15 if operation in DRAFT_LOGIN_SHORT_OPERATIONS else 600 if operation in ('export', 'verify-import', 'terminal-assets', 'terminal-snapshot', 'terminal-snapshot-get', 'run-snapshot', 'run-snapshot-get') else 15 if operation in (
        'inspect', 'review-admission', 'stage-import', 'health', 'grant-create', 'grant-renew', 'grant-get', 'grant-close', 'credential-refresh-get', 'credential-status', 'credential-material', 'credential-identity', 'credential-usage-get', 'account-login-get', 'account-login-observe', 'account-login-code-receipt', 'account-login-snapshot', 'account-login-input', 'account-bound-identity', 'account-bound-login-get', 'account-bound-login-observe', 'account-bound-login-code-receipt', 'account-bound-login-snapshot', 'account-bound-login-input',
        'terminal-get', 'terminal-observe', 'terminal-send', 'terminal-input', 'terminal-conversation',
        'terminal-usage', 'terminal-passive', 'terminal-passive-ack', 'terminal-quota-state', 'terminal-quota-read', 'api-quota-read', 'project-history-capture',
        'terminal-capture', 'terminal-reconcile', 'terminal-verification-get', 'run-verification-get', 'run-project-facts', 'run-project-native', 'run-get', 'run-poll', 'run-quota-state', 'run-quota-read', 'run-artifact', 'run-files', 'run-file', 'run-stats', 'run-capture', 'run-session', 'run-refresh', 'run-refresh-get', 'run-owner-refresh-defer', 'continue-get', 'continue-input', 'continue-quota-state', 'continue-quota-read', 'continue-quota-control', 'continue-credentials') else 115
    if operation in ('export', 'verify-import', 'prepare-import', 'prepare-files'):
        timeout = None
    connection = _NodeConnection(data / 'node-agent/control.sock', timeout)
    try:
        connection.request('POST', '/operations/' + operation, body=raw,
            headers={'content-type': 'application/json', 'x-v3-node-token': token, 'connection': 'close'})
        response = connection.getresponse()
        try:
            maximum=response_limit(operation)
            value = strict_json(response.read(maximum + 1), maximum)
            if (response.status != 200 or type(value.get('ok')) is not bool
                    or value['ok'] and not isinstance(value.get('result'), dict)):
                raise ValueError('节点私有执行未确认，请核对原操作')
            return value
        finally:
            response.close()
    finally:
        connection.close()


def main() -> None:
    """以轻量固定入口转发本次SSH操作，实际执行只由原长驻服务持有。

    :return: None；标准输出沿原ok/result与固定脱敏错误合同。
    """
    try:
        if os.environ.get('V3_ROLE')!='node-control' or len(sys.argv)!=2:
            raise ValueError('节点私有客户端入口角色或操作无效')
        raw=sys.stdin.buffer.read(2*1024*1024+1)
        if len(raw)>2*1024*1024:
            raise ValueError('节点准备请求过大')
        result=node_agent_request(Path(os.environ['BENCH_DATA']),os.environ['V3_INTERNAL_TOKEN'],sys.argv[1],raw)
    except Exception as error:
        # 沿原SSH入口只公开故障类型，实际请求、认证与远端原文留在私有边界。
        result={'ok':False,'reason':'node_preparation_failed','error_type':type(error).__name__}
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))


if __name__=='__main__':
    main()
