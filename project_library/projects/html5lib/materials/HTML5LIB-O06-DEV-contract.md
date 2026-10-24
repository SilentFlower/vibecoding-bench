# 从真实HTML树收集原始URI并按首个base稳定解析及分组

对应路线16：真实walker收集href/src/poster/action及普通srcset，首base优先按urljoin解析、保原URI和重复分组；空/片段/未知scheme明确、data集合标未解析，不联网或猜路径。

请先阅读实际源码和公开复现，完成调查、澄清和兼容方案，获得确认后在同一工作区实现。失败时依据独立反馈返工；测试和说明不是单独目标。
