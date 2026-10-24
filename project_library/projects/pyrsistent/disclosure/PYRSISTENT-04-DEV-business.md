# 业务确认

路线05：默认CheckedPMap键值和checked序列serializer递归传递真实format，多层容器与直接记录输出政策一致。自定义__serializer__仍接管，默认None不变，不假称任意序列化键可哈希。

请先调查、澄清并确认方案再实施。公开样例不是全部验收边界；独立失败必须返工。
