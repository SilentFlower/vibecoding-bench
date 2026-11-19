"""节点管理接口，浏览器只接收明确列举的公开字段。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from docker.errors import DockerException

from cluster_nodes import NodeAddress, NodeCreate, NodeEnabled, NodeRevision
from cluster_deployment import NodeInstallationConfigurationError
from cluster_ssh import probe_host_keys


class NodeRoute(APIRoute):
    """阻止请求校验异常回显节点私钥等输入。

    :param args: FastAPI 原路由参数。
    :param kwargs: FastAPI 原路由配置。
    """

    def get_route_handler(self):
        """包装默认路由的参数错误响应。:return: 不回显输入值的异步处理器。"""
        handler = super().get_route_handler()

        async def safe_handler(request: Request):
            try:
                return await handler(request)
            except RequestValidationError:
                return JSONResponse({'detail': '节点参数无效，请核对地址、身份、认证材料和配置版本'}, status_code=422)
        return safe_handler


def cluster_router(service) -> APIRouter:
    """创建沿用中央管理员会话的节点管理路由。

    :param service: 返回当前 ClusterService 的回调。
    :return: 节点资源路由。
    """
    router = APIRouter(prefix='/api/nodes', route_class=NodeRoute)

    def current():
        instance = service()
        if instance is None:
            raise HTTPException(503, '节点管理服务尚未就绪')
        return instance

    @router.get('')
    def list_nodes() -> dict:
        """列出节点公开状态。:return: 节点列表。"""
        return {'items': current().store.list()}

    @router.post('/synchronize', status_code=202)
    def synchronize_nodes() -> dict:
        """提交当前批次的统一节点后台同步。:return: 可轮询节点状态。"""
        try:
            return current().synchronize_nodes()
        except (ValueError, RuntimeError):
            raise HTTPException(409, '节点同步服务正在维护，请稍后查看原任务') from None

    @router.post('/host-keys')
    def host_keys(body: NodeAddress) -> dict:
        """探测候选公钥供管理员核对。:param body: SSH 地址。:return: 主机公钥与指纹。"""
        current()
        try:
            return {'items': probe_host_keys(body)}
        except ValueError as error:
            raise HTTPException(400, str(error)) from None

    @router.post('', status_code=201)
    def create_node(body: NodeCreate) -> dict:
        """登记已确认身份的节点。:param body: 节点配置与只写认证材料。:return: 公开节点。"""
        try:
            return current().register(body)
        except (ValueError, OSError):
            raise HTTPException(400, '节点登记失败，请核对认证材料、主机身份和重复节点') from None

    @router.post('/{node_id}/check')
    def check_node(node_id: int, body: NodeRevision) -> dict:
        """检查指定配置版本的节点。:param node_id: 节点。:param body: 版本。:return: 公开状态。"""
        try:
            return current().check(node_id, body.revision)
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    @router.put('/{node_id}/enabled')
    def enable_node(node_id: int, body: NodeEnabled) -> dict:
        """调整新工作接纳。:param node_id: 节点。:param body: 版本及新状态。:return: 公开状态。"""
        try:
            return current().store.set_enabled(node_id, body.revision, body.enabled)
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    @router.post('/{node_id}/prepare', status_code=202)
    def prepare_node(node_id: int, body: NodeRevision) -> dict:
        """提交后台组件安装。:param node_id: 节点。:param body: 版本。:return: 可轮询的公开状态。"""
        try:
            return current().prepare_node(node_id, body.revision)
        except NodeInstallationConfigurationError as error:
            raise HTTPException(409, str(error)) from None
        except (ValueError, OSError, RuntimeError, DockerException):
            raise HTTPException(409, '节点组件安装未完成，请核对配置、镜像、SSH 身份及远程数据归属') from None

    @router.delete('/{node_id}')
    def remove_node(node_id: int, body: NodeRevision) -> dict:
        """移除无引用远程节点。:param node_id: 节点。:param body: 版本。:return: 完成回执。"""
        try:
            current().remove(node_id, body.revision)
            return {'ok': True}
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    return router
