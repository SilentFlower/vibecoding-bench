# 节点目标镜像完整性实施

1. 复现同 ID 只含索引的情况，核对 Docker 29 的目标平台归档、导入及重读结果。
2. 修正共享镜像准备入口和停机顺序。覆盖健康复用、同 ID 残缺补齐、完全缺失、同名冲突、补齐后验证失败。
3. 在仓库根运行 `PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest test_cluster_synchronization test_cluster_node_docker`。用隔离 Docker 重放真实导入和原节点同步，核对健康回执及旧角色停止时点。
4. 核对失败恢复和既有 SSH 版本支持。交付修复版本后沿原部署流程验证 main。
