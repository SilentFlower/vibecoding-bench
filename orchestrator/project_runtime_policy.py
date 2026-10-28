"""共享 Python 兼容规则及可公开的环境准备故障。"""
from __future__ import annotations

import re


class ProjectRuntimeError(ValueError):
    """携带明确恢复语义，避免用错误文案决定调度。

    :param code: 控制端固定的原因标识。
    :param message: 可公开的中文原因。
    :param retryable: 是否允许调度器稍后重试。
    :param phase: 故障发生的执行阶段。
    :param details: 不含凭据及私有路径的事实。
    """

    def __init__(self, code: str, message: str, *, retryable: bool = False,
                 phase: str = 'preparing', details: dict | None = None) -> None:
        """保留控制端事实，不复制底层异常正文。

        :param code: 固定原因标识。
        :param message: 公开原因。
        :param retryable: 是否可按计划恢复。
        :param phase: 准备、启动或收口阶段。
        :param details: 公开事实。
        :return: None。
        """
        super().__init__(message)
        self.code, self.phase, self.retryable = code, phase, retryable
        self.details = details or {}


def python_versions_match(expected: str, actual: str, policy: str = 'minor') -> bool:
    """比较正常 Python 发布版本，默认容忍补丁差异。

    :param expected: 冻结验证版本，可为主次或完整版本。
    :param actual: 实际解释器版本。
    :param policy: minor 比较主次，exact 比较完整版本。
    :return: 两个版本均合法且满足策略时为 True。
    """
    if policy not in ('minor', 'exact') or not isinstance(expected, str) or not isinstance(actual, str):
        return False
    pattern = r'([1-9][0-9]*)\.(0|[1-9][0-9]*)(?:\.(0|[1-9][0-9]*))?'
    left, right = re.fullmatch(pattern, expected), re.fullmatch(pattern, actual)
    if not left or not right:
        return False
    return left.groups()[:2] == right.groups()[:2] if policy == 'minor' else left.groups() == right.groups()


def python_plugins_match(expected: list[dict], actual: list[dict], policy: str = 'minor') -> bool:
    """允许标准库的兼容补丁版本差异，其余插件元数据保持精确匹配。

    :param expected: 冻结合同中的有序插件元数据。
    :param actual: 当前运行时实测的有序插件元数据。
    :param policy: 标准库使用的 Python 版本兼容策略。
    :return: 插件身份、源码摘要及非标准库版本均符合合同时为 True。
    """
    if (policy not in ('minor', 'exact') or not isinstance(expected, list)
            or not isinstance(actual, list) or len(expected) != len(actual)):
        return False
    for frozen, observed in zip(expected, actual):
        if not isinstance(frozen, dict) or not isinstance(observed, dict):
            return False
        if frozen.get('distribution') == observed.get('distribution') == 'stdlib':
            if not python_versions_match(frozen.get('version'), observed.get('version'), policy):
                return False
            # 标准库版本随解释器变化；只归一化版本，保留源码摘要及全部其他字段的校验。
            observed = {**observed, 'version': frozen['version']}
        if frozen != observed:
            return False
    return True


def check_python_runtime(profile: dict, actual: str) -> dict:
    """核对实际版本并返回独立的运行证明。

    :param profile: 含冻结 python 和可选兼容策略的档案。
    :param actual: 实际探测得到的版本。
    :return: 可持久化、可公开的期望及实际版本与策略。
    """
    expected, policy = profile['python'], profile.get('python_compatibility', 'minor')
    details = {'expected_python': expected, 'actual_python': actual, 'python_compatibility': policy}
    if not python_versions_match(expected, actual, policy):
        raise ProjectRuntimeError('python_incompatible',
            f'Python 版本不兼容：验证版本 {expected}，实际版本 {actual or "未知"}，'
            + ('要求精确版本' if policy == 'exact' else '要求主次版本一致'), details=details)
    return details
