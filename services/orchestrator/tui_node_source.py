"""按实际 sender 装配区分节点 V2 事件源，探测只访问状态端点。"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from runtime_names import account_container_prefix
from system_update_contract import safe_read, strict_json


class _NoRedirect(HTTPRedirectHandler):
    """状态探测受原 sender URL 限制。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """保留原 HTTP 错误。@param req 原状态请求。@return 交由 urllib 处理的空重定向。"""
        return None


def _sender_document(root: Path, scope: dict, generation: int) -> dict:
    config = strict_json(safe_read(root / 'runtime/sender/sender.json'))
    binding = config.get('binding')
    expected = {'account_id': scope['gateway_account_id'], 'environment_id': scope['environment_id'],
        'generation': generation, 'release_id': scope['release_id']}
    if (not isinstance(config.get('tui_v2'), dict) or not isinstance(binding, dict)
            or any(type(binding.get(key)) is not type(value) or binding.get(key) != value
                   for key, value in expected.items())):
        raise ValueError('V2 已选事件源的账号绑定不可核验')
    return config


def _provider_mode(config: dict) -> str:
    if config.get('tui_host_memory') and not config.get('tui_managed_oauth'):
        return 'local_provider'
    return 'formal'


def _ready_sender(config: dict, scope: dict) -> bool:
    binding = config['binding']
    node = None if scope['node_key'] == 'local' else scope['node_key']
    hosts = [account_container_prefix(scope['deployment'], node_key=node)]
    if node is None:
        hosts.append(account_container_prefix(scope['deployment'], legacy=True))
    allowed = {f'http://{prefix}{scope["environment_id"]}:8091' for prefix in hosts}
    secret = binding.get('secret')
    if binding.get('endpoint') not in allowed or not isinstance(secret, str) or len(secret) < 32:
        return False
    request = Request(binding['endpoint'] + '/internal/status', headers={'Authorization': 'Bearer ' + secret})
    with build_opener(ProxyHandler({}), _NoRedirect()).open(request, timeout=3) as response:
        status = strict_json(response.read(65537), 65536)
    tui = status.get('tui_v2')
    return (isinstance(tui, dict) and type(tui.get('protocol')) is int and tui['protocol'] == 1
        and type(tui.get('account_id')) is int and tui['account_id'] == binding['account_id']
        and tui.get('release_id') == binding['release_id'] and tui.get('ready') is True
        and tui.get('event_source') == 'local_unix' and tui.get('idle') is True
        and type(status.get('active')) is int and status['active'] == 0
        and status.get('environment_id') == binding['environment_id']
        and type(status.get('generation')) is int and status['generation'] == binding['generation'])


def inspect_tui_node_source(data: Path, client, image: str, scope: dict) -> dict:
    """读取节点正式来源能力。@param data 节点私有根。@param client 节点 Docker。
    @param image 已选账号镜像。@param scope 调度器冻结的账号及环境。@return 无凭据的模式或就绪。
    """
    environment = scope['environment_id']
    if not re.fullmatch(r'[a-f0-9]{32}', environment):
        raise ValueError('V2 事件源环境身份无效')
    root = data / 'environments' / environment
    action, generation = scope['action'], scope['generation']
    if action == 'source':
        if scope['node_key'] != 'local':
            owner = strict_json(safe_read(root / 'runtime/node-assignment.json', private=True))
            if owner != {'protocol': 1, 'phase': 'ready', 'node_key': scope['node_key'],
                         'account_id': scope['account_id'], 'environment_id': environment, 'revision': scope['revision']}:
                raise ValueError('V2 源节点的运行绑定归属不一致')
        config = _sender_document(root, scope, generation)
        return {'mode': _provider_mode(config)}
    if action == 'target':
        metadata = client.images.get(image).attrs['Config'].get('Labels') or {}
        if metadata.get('vibebench.tui-sender-protocol') != '1' or metadata.get('vibebench.release') != scope['release_id']:
            return {'supported': False}
        if scope['mode'] == 'local_provider':
            from account_isolation import tui_node_provider
            return {'supported': (metadata.get('vibebench.tui-session-host') == '1'
                                  and tui_node_provider(data, environment) is not None)}
        # 空节点在此阶段只能证明已安装同发行 sender；实际事件源由提交前验收。
        return {'supported': scope['mode'] == 'formal'}
    if action != 'prepared':
        raise ValueError('V2 节点事件源探测动作无效')
    staged = strict_json(safe_read(root / 'runtime/node-migration-target.json', private=True))
    expected = {'operation_id': scope['operation_id'], 'node_key': scope['node_key'],
        'environment_id': environment, 'account_id': scope['account_id'], 'revision': scope['target_revision'],
        'phase': 'prepared', 'generation': generation}
    if any(type(staged.get(key)) is not type(value) or staged.get(key) != value for key, value in expected.items()):
        return {'ready': False}
    config = _sender_document(root, scope, generation)
    return {'ready': _provider_mode(config) == scope['mode'] and _ready_sender(config, scope)}
