# 实施与验收

1. 核对节点现有鉴权、名称校验、版本写入和节点操作锁。在 `cluster_nodes.py`、`cluster_store.py`、`cluster_api.py` 及节点页补齐改名入口，验证停用节点也能改名和陈旧表单冲突。
2. 在 `cluster_store.py` 和 `cluster_service.py` 调整移除的预检、终态历史判断和持久操作收据，与 `cluster_migrations.py`、节点同步和归属分配对齐在途准入。保留中央历史查询，处理已归档节点的远程文件请求。
3. 在现有 SSH 和节点运维边界增加按原归属清理与续接。先以合成双节点宿主校验绑定目录、运行角色、断线及幂等，再接入前端确认文案、轮询和失败续接。
4. 运行 `test_cluster_nodes.py`、`test_cluster_node_ops.py`、`test_cluster_migrations.py`、`test_cluster_synchronization.py` 和相关节点 API 回归。补充隔离测试，验证仅清理目标节点、终态历史可查、真实归属账号阻止移除、安装与迁移竞态、重复提交、SSH 中断以及相同地址重新登记。
5. 运行前端构建和节点页浏览器回归，覆盖改名、危险操作作用域提示、进度、错误恢复、账号归属移除门禁。生产绿云日本只用作问题定位，清理验证使用独立测试节点。
