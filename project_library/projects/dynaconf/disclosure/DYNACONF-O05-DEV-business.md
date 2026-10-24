# 业务确认

对应路线09：实例set_value_parser接入真实tomlfy/env加载，支持json/literal/本地callable/None；显式token优先、非字符串不改，解析失败raise或保原文、编程异常传播且全局不污染。

方案确认后实施真实源码改动，公开样例不是全部验收边界。禁止修改原始测试、环境或独立验收器。
