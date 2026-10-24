# 异步LRU只缓存成功await结果并隔离loop及清理代次

路线03：独立async_lru_cache缓存成功完成值，各loop独立有界LRU；异常/取消不缓存，clear撤回在飞回填，正常async descriptor/元数据保持，明确不合并并发计算。
