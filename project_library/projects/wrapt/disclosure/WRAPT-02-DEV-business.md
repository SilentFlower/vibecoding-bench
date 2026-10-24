# 业务确认

路线02：weak_method_cache显式弱引用外置存储，id+weakref核同一实例，支持slots/不可hash且不缓存boundmethod强引用；计数/定点清理与GC真实证明，不支持弱引用明确拒绝，结果自行保活self除外。

请先调查、澄清并确认方案再实施。公开样例不是全部验收边界；独立失败必须返工。
