# 编辑字典模板发布完整新版本并保留旧预览快照

路线02：新增显式版本化内存loader，update/delete原子发布、同内容不增版、旧模板/只读源码snapshot不变；有界LRU、真实环境身份及globals隔离，同步异步同锁内存操作，不改旧DictLoader合同。
