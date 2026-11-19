"""已结束工程的抓包资料按当前持久归属只读访问，独立于旧终端执行定位。"""
from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import Field, StrictInt, StrictStr

from capture_artifacts import capture_file_preview, capture_summary
from cluster_execution import NodeLocation


class ProjectHistoryCapture(NodeLocation):
    """当前环境内单一历史工作的受限抓包查询。

    :param generation: 已核对实际环境代次。
    :param namespace: 中央冻结的工程空间。
    :param work_id: 中央已结束工作身份。
    :param relative: 原读取器允许的文件预览。
    """

    generation: StrictInt = Field(ge=0)
    namespace: Literal['projects', 'warmup']
    work_id: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    relative: StrictStr | None = Field(default=None, max_length=4096)


def read_project_history_capture(executor, request: ProjectHistoryCapture) -> dict:
    """只读已迁移的工程抓包，保持原预览脱敏与路径限制。

    :param executor: 当前安装节点。
    :param request: 经中央工作归属核对的固定查询。
    :return: 绑定原查询的抓包摘要或受限文件。
    """
    with executor._locked(read_only=True, environment_id=request.environment_id):
        location = NodeLocation.model_validate(request.model_dump(include=set(NodeLocation.model_fields)))
        row = executor._inspection_row(location)
        if row['generation'] != request.generation:
            raise ValueError('历史工程抓包的环境代次已变化')
        root = executor.data / 'environments' / request.environment_id
        group = hashlib.sha256(f'{request.namespace}/{request.work_id}'.encode()).hexdigest()[:20]
        base = root / 'flows' / ('group-' + group)
        if any(path.is_symlink() for path in (root, root / 'flows', base)):
            raise ValueError('历史工程抓包目录归属异常')
        capture = capture_file_preview(base, request.relative) if request.relative is not None else capture_summary(base)
        return {'reference': request.model_dump(), 'capture': capture}
