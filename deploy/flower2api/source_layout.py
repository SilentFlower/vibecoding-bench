"""将单仓源码映射到稳定的 v3 构建和宿主安装布局。"""
from pathlib import Path


# 对外清单和已安装宿主继续使用左侧逻辑路径，源码搬迁只改变右侧来源。
SOURCE_ROOTS = (
    ('deploy/v3', 'deploy/flower2api'),
    ('cc2api/web', 'apps/web'),
    ('cc2api', 'services/gateway'),
    ('orchestrator', 'services/orchestrator'),
    ('webui', 'apps/legacy-web'),
    ('project_library', 'resources/project-library'),
    ('topics.md', 'resources/topics.md'),
    ('research/github-projects', 'resources/project-research'),
)


def source_path(root: Path, logical: str | Path) -> Path:
    """解析源码来源，同时支持旧构建快照和已安装的固定宿主包。

    :param root: 源码或冻结安装包根目录。
    :param logical: 原 v3 相对逻辑路径。
    :return: 新单仓来源路径，或旧布局中的对应路径。
    """
    relative = Path(logical)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('源码逻辑路径必须位于项目根内')
    for original, migrated in SOURCE_ROOTS:
        prefix = Path(original)
        if relative.is_relative_to(prefix):
            candidate = root / migrated / relative.relative_to(prefix)
            # 部署源码单独识别迁移，兼容已有 services 目录的上一版单仓和固定宿主包。
            marker = root / ('deploy/flower2api' if original == 'deploy/v3' else 'services')
            return candidate if marker.is_dir() else root / relative
    return root / relative
