# CRIU 热模板实施计划

## 执行顺序

- [x] 经 Brief 评审激活任务后，进入 trellis-route(target=implement)，使用 inline 执行并读取 trellis-before-dev 和任务引用规范。
- [x] 将研究用 CRIU 4.2 补丁与固定配方整理为可复现受控构建；核对依赖、功能开关、SHA 与许可，保留 stock CRIU 失败和 patched CRIU 成功对照。
- [x] 先完成同模板多次／四副本并发恢复实验，源进程保持存活；核对 PID 命名空间、独立目录、管道、权限、随机标识及原生配置缓存。将结果写入 research/，通过后继续接入。
- [x] 定义并实现版本化模板准备／恢复绑定协议，覆盖共享 WorkerCommand／WorkerFrame 解码、runtime 模板点、新实例握手、旧协议兼容及构建源清单。
- [x] 实现独立受控恢复器及受信任 IPC，覆盖模板登记、身份／代次校验、命名空间、继承 FD、实际 PID 所有权、私有文件权限和故障清理。
- [x] 整理 Worker 的物理进程所有权与管道类型，接入模板优先恢复及业务前正常启动回退；保留容量、单调截止、一次提交及退出后释放许可。
- [x] 接入账号代次、维护排空、服务关闭和内核切换的模板失效；同步部署配置与能力预检，保持业务 worker 受限身份。
- [x] 重新建立恢复实例的 TLS 观测归属，补全安全阶段诊断与实际消费者兼容。
- [x] 执行 A1～A7 与 A8 的回归验证，保存合成身份、隔离回环和真实 TLS 接收证据；至少二十轮采样完整准备及对照性能。
- [x] 经 trellis-route(target=check) 完成质量检查，修复 FBK-001 并定向重检；由 trellis-update-spec 同步恢复协议与物理退出合同。
- [x] 完成精确 Push 文件归属预检、计划确认及提交推送。

## 文件与合同检查

- gateway：native_runtime.rs、native_contract.rs、runtime_transport.rs、native_tls_observer.rs 及所有实际进程 PID／管道／诊断消费者。
- runtime：runtime/293/worker.ts、shared/contracts.ts、shared/protocol.ts、control/engine.ts、scripts/build-runtime.ts 及当前恢复能力的构建／封口消费者。
- orchestrator：account_isolation.py、native_sender.py、账号环境配置／维护／内核切换及对应测试。
- 新增受控恢复器和 CRIU 配方前先确定现有目录与模块复用方式；新增公开方法均有中文参数及返回值文档。

## 验证计划

gateway：

```bash
cargo fmt --check
cargo test --locked native_criu
cargo test --locked
```

runtime：

```bash
bun run typecheck
bun test tests/unit
bun run test:integration
```

orchestrator：

```bash
PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest discover -s services/orchestrator
```

- 实际测试名与构建命令以实施时读取的定义为准。跨层与新增协议同时验证正常 exec、恢复、失效回退及旧内核能力缺失。
- 真正 dump/restore 与受限身份测试在隔离 KVM 或通过能力预检的自有测试环境运行；普通单测和被跳过的测试单列。
- 上游仅使用合成账号和独立回环 HTTP/TLS 接收端，模板准备 POST 数为零，每业务 POST 数为一。
- 故障注入核对真实进程退出、所有权与物理计数，覆盖恢复中取消和控制器失联；保存安全摘要及受限权限证明。
- 性能对照统一 CPU、内存、内核、CRIU 配方、原生映像、业务输入和 TLS 采集条件，记录分位数及完整阶段，模板首建单列。

## 回退与交付边界

- 恢复来源、模板生命周期及绑定协议按一个完整行为单元验证；部署侧关闭恢复功能可返回现有正常启动路径。
- 生产发布、启用恢复器及改变真实环境权限在后续上线流程中处理。本轮交付代码、配方、部署预检、操作说明及隔离验证证据。

## 生成束与提交顺序

- CRIU canonical来源位于services/runtime/native/criu及scripts/criu；images/v3/criu由export_bundle.py生成，目标ABI由Dockerfile criu-build执行package.py。
- TLS canonical来源位于services/runtime/native/tls-observer；正式export_bundle.py要求相关源码已提交且路径干净。当前隔离验收使用显式development束，Docker验证相应显式允许开发束。
- Git完成链需要先提交已核验源码，再执行正式TLS导出，提交生成清单后统一推送。具体精确文件和生成命令在trellis-push计划中展示，沿其确认与归属规则执行。正式导出预期只改变manifest的来源revision与development标记，代码文件SHA保持已核验值。
