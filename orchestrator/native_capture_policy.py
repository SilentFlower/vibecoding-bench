"""原生内容采集的默认值由所有生命周期入口共同解释。"""


def capture_enabled(fingerprint: dict) -> bool:
    """缺省开启并保留显式关闭。@param fingerprint 账号固化配置。@return 目标状态；非法值拒绝。"""
    value = fingerprint.get('native_capture_enabled', True)
    if type(value) is not bool:
        raise ValueError('请求内容采集选择无效，请对账账号配置')
    return value
