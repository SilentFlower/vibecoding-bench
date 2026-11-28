"""在中央的内部认证路由上，按当前登记节点转交固定的停止观察。"""

import json
import os
import secrets

from fastapi import APIRouter, HTTPException, Request

from cluster_deployment import node_container_name
from cluster_stopped_observation import OPERATION, StoppedNodeRead, require_node_gate
from system_updates import update_token


def stopped_node_router(service_provider) -> APIRouter:
    """创建仅供宿主同代排空读取的中央接口。@param service_provider 已初始化节点服务。@return 内部路由。"""
    router = APIRouter()

    @router.post('/internal/v3/system-updates/stopped-node')
    def observe(request: Request, body: StoppedNodeRead) -> dict:
        """复核节点登记后通过原 SSH 通道读取。@param request 宿主认证。@param body 本次冻结范围。@return 脱敏节点观察。"""
        if not secrets.compare_digest(request.headers.get('x-v3-update-token', ''), update_token()):
            raise HTTPException(403, '更新服务证明无效')
        service = service_provider()
        if service is None or os.environ.get('V3_DEPLOYMENT_ID') != body.deployment:
            raise HTTPException(503, '节点控制服务尚未就绪')

        def registration():
            current = service.store.get(body.node_id)
            if (
                current['kind'] != 'ssh'
                or current['node_key'] != body.node_key
                or current['revision'] != body.node_revision
                or json.loads(current['preparation_json'] or '{}').get('removal')
            ):
                raise ValueError('节点登记已变化')
            return current['config_json']

        try:
            require_node_gate(body)
            before = registration()
            peer = service.connection(body.node_id)
            name = node_container_name(body.deployment, body.node_key)
            result = peer.execution_environment(name, body.model_dump(), OPERATION)
            if (
                result.get('challenge') != body.challenge
                or result.get('environment_id') != body.environment_id
                or result.get('profile_name') != body.profile_name
                or type(result.get('generation')) is not int
                or result['generation'] != body.generation
            ):
                raise ValueError('原节点观察未绑定本次挑战')
            # 两次读取间复核中央冻结和节点登记；外层快照另外核对完整拓扑与实际引擎。
            if registration() != before:
                raise ValueError('节点资料在取证期间变化')
            require_node_gate(body)
            return result
        except (ValueError, OSError, KeyError, RuntimeError):
            raise HTTPException(409, '原 SSH 节点冻结或停止观察未确认') from None

    return router
