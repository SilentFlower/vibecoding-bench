"""养号迭代复用工程引擎接口，任务空间由传入的独立服务决定。"""
from __future__ import annotations

from fastapi import APIRouter

from projects_api import projects_router


def warmup_pi_router(service) -> APIRouter:
    """在账号命名空间挂载完整工程接口，不创建题库控制器或独立路由协议。

    :param service: 返回养号命名空间 ProjectsService 的回调。
    :return: 与项目迭代一致的工程接口。
    """
    return projects_router(service, prefix='/api/accounts/warmup/pi')
