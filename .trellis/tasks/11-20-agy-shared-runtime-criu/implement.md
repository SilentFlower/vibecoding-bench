# 实施与验证

1. 在 `services/orchestrator/agy_runtime` 改受管进程的模型绑定。覆盖运行配置、监督器提交、私有信封、内核作业、历史投影和原工具收口。清点 `configure_model`、`CAPABILITIES`、`native_history` 的独立入口及测试消费者。
2. 调整监督器的热进程与模板选择、过期和补位。按 CC 的基础热进程与额外进程策略保留一个有效的热进程，额外进程使用 120 秒空闲期限。同步 `services/runtime/native/criu/agy.py`、`images/v3/criu/agy.py` 与制品源清单。在 Linux 6.1 隔离 OCI 夹具验证恢复连接继续持有退出责任时可以创建下一份快照，在监督器测试中验证旧代、满槽、120 秒内复用、到期缩池、基础热进程保留及失败回退。
3. 扩充网关 `NativeRuntimeObservation` 的可选启动来源，重检 AGY `request_prepared` 的 worker 和代次归属。覆盖历史缺字段和非法来源。使用实际阶段耗时核对最近扩容与热命中的区别。
4. 运行 `PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest test_agy_runtime test_agy_supervisor test_agy_system_prompt test_agy_environment test_native_criu_settings test_source_layout` 及 `python3 -m unittest discover -s services/runtime/native/criu`。Python 两组分别通过 77 项和 49 项。
5. 在 `services/gateway` 运行 `cargo fmt --check` 和 `cargo test --locked --lib --test agy_sender_test --test gemini_contract_test --test gemini_account_test --test runtime_transport_test -j 2`。真实网关回环分别执行 `verify_agy_native_loopback.py` 的 `--shared-models` 和默认工具续轮场景。使用同版本 Linux 6.1、CRIU 4.2 和固定 AGY 1.5.9 的隔离 OCI 验收，记录实际 worker/PID、模型、恢复和终态。
6. 核对代码与镜像源一致，做 Check-All。按实际验证事实补齐运行合同后进入交付。保留基线与产物可回退证据，生产应用交给本次明确范围对应的部署步骤。
7. 运行环境增加反重力账号名称投影。沿既有网关分页和页面标题字段，使用显式平台和准确账号 ID。执行环境汇总、账号解绑回归及 AGY 页面浏览器验收，再统一核对最终交付。

## 验证记录

- 网关回环的三个请求以 A、B、A 交替发送。三个实际出站模型分别对应目录，请求详情中的 PID 一致，后两次为热命中。工具回归包含跨凭据代次续轮、真实原生回填和重复回填拒绝。
- Linux 6.1 隔离 OCI 使用正式绑定路径、实际 CRIU 和固定原版。模型 A 零业务准备的模板供模型 B 以原 PID 恢复，原进程继续运行时补出了第二份模板。保存失败、恢复失败和凭据换代分别验证普通启动路径各只发送一次合成模型请求。空闲回收边界由监督器测试推进时间验证。
- 常规 Rust 回归通过 913 项，8 项独立夹具由 lib 默认标记忽略。改动的 Rust 文件通过格式检查。全库格式检查报告的偏差位于既有文件。
- 对齐 CC 回收策略后的定向回归通过 77 项。线程测试核对额外进程在 119 秒时可分配，在 120 秒时回收。基础热进程空闲超过 300 秒仍可用，凭据失效后回收。同版本真实网关回环继续通过跨模型同 PID 验收。
- 补齐账号名称查询后的最终编排回归通过 174 项，覆盖反重力分页、错平台、查询失败及原解绑。浏览器在 1440、720 和 390 像素宽度验证卡片、详情、原资源表单及离页轮询。新回收策略下的 Linux 6.1 隔离验收再次通过恢复、补位、保存失败、恢复失败和换代。
- 隔离日志保存在本地 `.trellis/.runtime/agy-shared-runtime-criu-01a1f914/`。部署后由发布操作者复核 US #14 的同账号跨模型 PID、模板补位以及请求详情中的实际启动来源。
