# 把JSONliteral或本地值解析器限制到当前实例的真实加载路径

对应路线09：实例set_value_parser接入真实tomlfy/env加载，支持json/literal/本地callable/None；显式token优先、非字符串不改，解析失败raise或保原文、编程异常传播且全局不污染。

请先阅读实际源码和公开复现，完成调查、澄清和兼容方案，获得确认后在同一工作区实现。失败时依据独立反馈返工；测试和说明不是单独目标。
