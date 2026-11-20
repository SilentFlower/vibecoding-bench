# 实施计划

## 顺序

- [x] 完成Brief评审后激活任务，通过 `trellis-route(target=implement)` 进入inline实施并加载 `trellis-before-dev`。
- [x] 读取相关结构及资源入口，删除Python与Rust三处普通exec最低内存公式，独立保留正worker及资源真实性检查。
- [x] 调整Python旧预算负例、Rust配置准入及真实二进制负例，覆盖历史单版、双版和unlimited。
- [x] 同步资源字段注释及当前部署文档，保留CRIU独立恢复规则与旧故障码兼容。
- [x] 完成定向检查后经 `trellis-route(target=check)` 进入Check-All，完成全面重检和Spec复核并进入精确Push计划。

## 验证

仓库根执行Python资源与账号生命周期回归：

```bash
PYTHONPATH=services/orchestrator .venv/bin/python -m unittest test_native_sender test_native_criu_settings test_account_runtime
```

在 `services/gateway` 执行Rust定向回归：

```bash
cargo test --locked service::native_runtime::tests --lib
cargo test --locked service::runtime_transport::tests --lib
```

新增或调整的准入用例应直接覆盖低于旧公式的有限配置；身份、非法路径、零worker及跨版容量用例直接断言原拒绝或上限。相关忽略测试的真实启动验证沿仓库已有离线夹具及本地TLS进行，环境变量与制品路径以现有定义为准。使用合成凭据，零外部模型调用。Check-All按实际行为影响选择深度并复用本轮有效证据。

## 文档与回退点

当前README及两份资源合同均需排查单版/双版最低公式。CRIU章节只同步普通exec描述，恢复门槛保持现状。`native_contract.rs` 的memory_mib说明与执行语义一起更新。

风险集中于删错恢复公式、漏掉版本选择入口及把旧资源负例改为实际发送。逐项对照R1～R5检查，真实负例保持发送数为0。原397项未提交文件逐项核对保留，新任务材料独立纳入后续精确范围。

## Check-All修复续行

- [x] CHK-001：封禁命中等待完整UPDATE RETURNING结果，独立连接立即读取计数；队列用例明确断言session_policy_blocked。
- [x] 运行 `cargo test --locked --lib session_policy_block -- --test-threads=1`，核对封禁服务、存储及排队路径。
- [x] 完成必要全量复核并按原ID重检，记账后台修复回执后进入Spec和Push。

## 验证记录

- Python定向126项通过；仓库根 `PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest discover -s services/orchestrator` 运行1313项，跳过1项，退出0。本地日志为 `/tmp/native-sender-memory-python.log` 和 `/tmp/native-sender-memory-python-full.log`。
- 初轮Rust全量出现排队计数断言失败，隔离及已发布cb5a1615原源码均复现；保留对应原始日志。CHK-001修复后15项封禁定向通过。
- 在 `services/gateway` 运行 `cargo test --locked -- --test-threads=4`，最终库测试838通过、5跳过，集成86通过、4跳过，文档测试通过，退出0。本地日志 `/tmp/native-sender-memory-rust-final.log`。
- 既有 `services/runtime/scripts/testing/cc2api-native.ts` 离线夹具使用合成凭据、本地TLS及固定293 beta.6/280制品，冻结有限配置128MiB；单版实收28次、混合实收18次，峰值并发均6，退出0。日志 `/tmp/native-sender-memory-single.log`、`/tmp/native-sender-memory-mixed.log`，实收摘要为同前缀json。此数值是配置，独立内存测量保持原口径。
- `cargo fmt --check`、`git diff --check`及规范六节结构/索引/新增链接检查通过。全面重检通过，CHK-001已解决，DOC-001已同步。当前Spec已覆盖行为，收尾Spec复核结果为no-op。
