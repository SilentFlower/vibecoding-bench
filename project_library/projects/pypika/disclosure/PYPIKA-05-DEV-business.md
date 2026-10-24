# 业务确认

路线07：parameter等序列化上下文进入每个函数参数，统一嵌套with_alias/subquery；聚合FILTER和WHERE保持真实遍历顺序，SQLite实际绑定执行。

请先调查、澄清并确认方案再实施。公开样例不是全部验收边界；独立失败必须返工。
