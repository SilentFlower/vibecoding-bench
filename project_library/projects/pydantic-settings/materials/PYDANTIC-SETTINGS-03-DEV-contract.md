# 冻结集合与队列配置通过真实CLI序列化后完整恢复

路线03：frozenset和deque真实CLI往返保类型、顺序/重复、空值及完整JSON转义；仅新容器的完整JSON按标准解码一次，旧简写/其它容器/NoDecode政策不变。
