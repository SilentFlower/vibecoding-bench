# 无字典轻量实例以弱引用身份维护独立方法缓存

路线02：weak_method_cache显式弱引用外置存储，id+weakref核同一实例，支持slots/不可hash且不缓存boundmethod强引用；计数/定点清理与GC真实证明，不支持弱引用明确拒绝，结果自行保活self除外。
