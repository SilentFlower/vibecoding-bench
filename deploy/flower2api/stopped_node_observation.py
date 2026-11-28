"""固定宿主沿原认证编排及网关入口取得单个 SSH 节点的停止观察。"""


def observe_stopped_node(host, scope: dict, node: dict) -> dict:
    """读取实时节点回执，并独立确认全网关待工具回执。@param host 原宿主控制器。@param scope 冻结范围。@param node 登记节点。@return 节点停止证据。"""
    if (
        node.get('kind') != 'ssh'
        or [item for item in scope['nodes'] if item.get('id') == node['id']] != [node]
        or host.policy['deployment'] != scope['deployment']
    ):
        raise ValueError('宿主冻结的 SSH 节点身份待核对')

    def gateway_idle():
        status = host.request('gateway', '/admin/runtime/system-update/status')
        if (
            status.get('phase') != 'blocked'
            or status.get('operation_id') != scope['operation_id']
            or status.get('epoch') != scope['epoch']
            or type(status.get('active')) is not int
            or status['active'] != 0
            or status.get('tui_tool_pending') is not False
        ):
            raise ValueError('网关仍有活动、待工具回执或门禁归属变化')
        return int(status['tui_tool_pending'])

    gateway_idle()
    keys = (
        'deployment',
        'operation_id',
        'epoch',
        'challenge',
        'environment_id',
        'generation',
        'profile_name',
        'role_ids',
    )
    request = {
        **{key: scope[key] for key in keys},
        'node_id': node['id'],
        'node_key': node['node_key'],
        'node_revision': node['revision'],
    }
    result = host.request('orchestrator', '/internal/v3/system-updates/stopped-node', request)
    if (
        result.get('protocol') != 1
        or result.get('node_key') != node['node_key']
        or any(
            result.get(key) != scope[key]
            for key in ('challenge', 'environment_id', 'generation', 'profile_name', 'operation_id', 'epoch')
        )
        or result.get('phase') != 'blocked'
    ):
        raise ValueError('SSH 节点观察回执归属不一致')
    pending_receipts = gateway_idle()
    # 待工具状态由唯一网关持有。明确 False 才能报告精确零，active=0 本身不能证明回执收口。
    fields = (
        'phase',
        'operation_id',
        'epoch',
        'engine_id',
        'directories',
        'binding',
        'jobs',
        'executions',
        'leases',
    )
    return {**{key: result[key] for key in fields}, 'pending_receipts': pending_receipts}
