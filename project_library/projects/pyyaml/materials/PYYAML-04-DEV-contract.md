# 未知YAML标签可作为安全数据保留并往返转储

路线08：未知标签存TaggedValue(tag/种类/安全值)，标量原文及递归/共享别名保真，明确dumper读回；python/object/apply也只是惰性数据，不导入执行，默认safe拒绝保持。
