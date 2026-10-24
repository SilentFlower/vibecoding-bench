# 严格安全配置加载拒绝显式重复字段并给出双位置

路线05：独立StrictSafeLoader对同映射显式键在flatten前检查，语义碰撞给首次/再次位置；merge继承+本地覆盖合法，默认safe_load后值胜出保持。
