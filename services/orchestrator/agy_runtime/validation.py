"""保持原生归属和序号校验在Python优化模式下生效。"""


def require(condition: bool) -> None:
    """校验原生内部不变量。@param condition 必须成立的归属或顺序条件。@return 无。"""
    if not condition:
        raise ValueError('AGY原生归属或流顺序无效')
