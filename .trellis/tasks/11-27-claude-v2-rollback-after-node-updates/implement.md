# 实施和验证

1. 核对线上 v1.40.1 对应的源码和目标分支。现有工作区同时在修改网关路由与编排，实施时隔离本任务补丁，保留已有改动。
2. 复用 `cluster_service.py` 的换版证据解析与 `cluster_synchronization.py` 的已完成维护归档。按同分配冻结的账号和代次串联受信记录。为回切查询返回必要的前驱凭据。使用现有本机、SSH 环境锁与角色核验补充已停止回切的私有结果。
3. 在 `tui_backend.rs`、`runtime_transport.rs` 接入回切核验，复用原账号门禁和比较写，保持管理响应和旧轮核对的行为。验证已存在的待切目标无需让用户重新选择。
4. 在 `services/gateway` 运行 `cargo test --locked tui_backend` 和 `cargo test --locked tui_`。从仓库根运行 `PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest test_tui_node_transition test_cluster_synchronization test_cluster_transport`。
5. 使用本地候选网关与隔离账号镜像运行 `deploy/flower2api/verify_tui_sender_status.py --gateway <网关二进制> --account-image <隔离账号镜像>` 所用的真实管理和发送链路。覆盖接单开关、停止、运行、跨两次换版、重建、后台对账、旧轮及 V1 首个合成请求。用编排回归复现再次升级失败并恢复原发行，核对同一绑定能继续读取已完成的归档。记录可重跑证据并进入 Check-All。
