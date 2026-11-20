"""轻量 SSH 入口与 Node 共用的具体环境管理操作。"""

ENVIRONMENT_OPERATIONS = (
    'environment-state', 'environment-cpu-read', 'environment-cpu-set',
    'environment-physical-refresh', 'environment-capture-read',
    'environment-capture-settings', 'environment-capture-set',
    'environment-criu-settings', 'environment-criu-set', 'environment-maintenance',
)


def response_limit(operation: str) -> int:
    """按原持久快照预算选择有界私有响应大小。

    :param operation: 固定私有操作名。
    :return: 请求快照允许原6MiB文件及JSON信封，其余容纳原2MiB列表及JSON信封。
    """
    return 8 * 1024 * 1024 if operation in ('environment-capture-read', 'agy-capture-read') else 4 * 1024 * 1024
