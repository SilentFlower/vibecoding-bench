# 反重力并发在线调整实施

1. 从账号表单的提交载荷追到 `update_account`、`update_agy_fields` 及 `AccountQueue`。核对并发独立更新和混合字段的校验顺序，覆盖未变代理、真实代理变更及权限回归。
2. 接通编排器至已登记发送器的容量更新和读回。按真实代次核对配置、物理池和角色限制，覆盖正在预热、模板就绪、已接单和待回填状态。复用原预算及配置写入，防止新增每请求控制调用。
3. 贯通扩容与缩容的生效顺序。为失败、重复提交、迟到回包及重启复核同操作结果。覆盖停止后首次唤醒与现有环境恢复。
4. 执行 `services/orchestrator` 的 `python3 -m unittest test_agy_environment test_agy_supervisor test_agy_runtime` 及 `services/gateway` 的 `cargo test --locked --lib --test gemini_account_test --test agy_sender_test`。增加覆盖跨进程容量生效和失败恢复的定向回归。
5. 用隔离 AGY 账号从真实管理入口执行 3→4→3。检查第 4 个请求实际接单、原容器和进程归属保持、在途工具回填收口、有限预算拒绝的可操作提示。将同一账号与场景交给节点迁移联合复核。

## 核验记录

- `verify_agy_native_loopback.py --live-capacity` 在断网容器通过真实网关、发送器和 AGY 1.5.9 接入合成 TLS 上游。3 路在途时第 4 笔排队，扩容后实际接单。缩容后等待到可用名额再发送第 5 笔。五笔各提交一次，监督器保持同一 PID。
- `--shared-models` 的三次模型切换沿同一个原生 PID，热命中依次为 false、true、true。
- 真实 Docker 资源更新中，有限发送器角色保持容器主进程，RAM 为 1280→1536→1280 MiB，PID 限额为 320→384→320。工具轮收尾、回包丢失及延后回收额度由独立编排和监督器回归覆盖。
- 正式版本部署后，管理员在目标部署核对运行时支持和账号的实际容量。节点迁出、远程热更和迁回由同批节点迁移子任务验收。
