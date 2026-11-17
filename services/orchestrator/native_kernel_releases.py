"""保留历史导入兼容，独立内核发行发现已经退役。"""


def discover_releases(refresh: bool = False) -> dict:
    """返回退役说明。@param refresh 历史兼容参数。@return 平台管理标记。"""
    return {'state': 'retired', 'management': 'platform', 'versions': [], 'latest': None}
