# 实施验收证据

## 验收映射

| 验收 | 实现边界 | 已执行证据 |
| --- | --- | --- |
| A1 | Controller模板登记、两阶段FD、独立PID/挂载空间；worker_restore_bind | bookworm-tls-fault-summary.json：同源存活，串行3/并发4，七笔独立请求；same-template-binding-summary.json补充独立目录/管道/随机源 |
| A2 | 每次作业沿原生独立根；多进程单作业 | 七会话/两模型/独立响应，每笔一次POST；runtime单测187通过；集成CCH/会话/上下文覆盖，超时两项独立重跑通过 |
| A3 | pool_identity覆盖配置、凭据和身份；控制租约及快照完整性；固定内核能力 | 代理/环境代次/内核身份定向断言；旧代池切换原测试；五类非法身份或字段、污染/过期模板拒绝；正常路径兼容旧内核 |
| A4 | entry预检、固定降权入口、控制peer/种子PID/env/exec校验 | 实际控制器CapEff032c11eb/NNP1/seccomp0；业务UID1001/cap0/NNP1/seccomp2；错误PID/path、非权威对端拒绝；隔离网络只有回环 |
| A5 | RestoreGuard/Worker独立清理、namespace pidfd、模板注销/退避 | ACK前后取消、真实取消守卫许可保留、控制器SIGKILL/重启回收；NativePool完整submit失效模板exec回退且恰好一笔POST |
| A6 | TLS Broker恢复所有权登记；目标active PID namespace | 七笔TLS最终正文与规范化头摘要独立等于实收，外部物理PID一致；cc_prepared的CCH差异单列 |
| A7 | 实际entry、NativePool checkout、映像核验、绑定、TLSready | bookworm-entry-paired-summary.json保存20轮交替配对、源首次成本与阶段采样；完整p50门槛通过；CRIU命令及熵画像计时在controller私有日志 |
| A8 | 配方、部署、生成束与调用方 | 目标Bookworm Docker构建、依赖/全部文件SHA检查、容器预检失败受限exec回退；Rust/runtime/orchestrator/deploy回归；Spec已同步恢复协议1的六节合同 |

## 验证命令与结果

实际日志根 `/tmp/flower2api-criu-research-9amnj8l_/`。命令均使用合成身份或只读/本地资源。

| 范围 | 命令与工作目录 | 结果与日志 |
| --- | --- | --- |
| gateway全量 | services/gateway，cargo test --locked | 881通过、9忽略；gateway-all-tests.log；其后恢复失败撤销/旧代模板选择及阶段计时由下两项覆盖 |
| gateway当前定向 | services/gateway，cargo test --locked --lib native_criu | 4通过、1显式隔离测试忽略；eof-regression-after.log。真实pidfd的EOF日志回归在修复前失败、修复后通过；普通Child错误/EOF/截止定向另1项通过，eof-direct-regression.log |
| gateway隔离测试 | release native_criu_isolated_paired_preparation --ignored --exact --nocapture | 实际可信入口/KVM运行，通过20配对及完整回退；bookworm-entry-console.log；忽略只指普通测试套件 |
| runtime类型/单测 | services/runtime，bun run typecheck；bun test tests/unit | 187通过、1870断言；runtime-typecheck.log、runtime-unit.log |
| runtime集成 | services/runtime，bun run test:integration | 第一轮49通过/1组失败，组内两项在并发重载时超时；单独重跑两项通过、85断言，耗时约82秒；runtime-integration.log、runtime-pool-retry.log |
| orchestrator | 根目录，PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest discover -s services/orchestrator | 1240测试，OK/skip1；orchestrator-tests.log |
| deploy当前范围 | 根目录，同PYTHONPATH，.venv/bin/python -m unittest deploy.flower2api.test_manage deploy.flower2api.test_native_tls_isolation deploy.flower2api.test_system_release deploy.flower2api.test_source_layout | 52通过；deploy-final-tests.log |
| CRIU合同/构建 | python3 -m unittest discover -s services/runtime/native/criu -p 'test_*.py'；scripts/criu同类命令 | 12+3通过；criu-unit-final.log、criu-build-unit-final.log |
| observer | Python test_broker与test_http_capture | 14通过，含嵌套PID与清理二次取消回归 |
| 目标ABI | docker build --target criu-build -f images/v3/Dockerfile -t flower2api-criu-verify:20261113 . | 真实Bookworm/GCC12构建，全部包文件SHA一致；criu-docker-final.log、bookworm-build-provenance.json |
| 受限容器回退 | 自有只读、无网络容器，SETUID/SETGID，继承seccomp2 | RESTORE_PREFLIGHT_FAILED后CCRB_CRIU0；实际业务UID1001/cap0/NNP1/seccomp2；criu-container-fallback.log |

## 交付与后续边界

- 版本化复跑夹具和客体资产说明位于 verification/。原始快照、官方源码、二进制、完整请求和临时私钥保留在隔离临时目录。
- TLS生成束已在源码提交后通过正式导出器生成，development=false，来源revision绑定已提交源码；代码文件SHA保持已验收值。合并源码与正式清单已推送。
- 生产启用属于后续上线流程。目标环境须验证13项控制器能力、内核恢复、内存峰值与并发准备时延，并沿现有签名内核流程激活协议1候选。
- 四副本的正确性验证在2vCPU客体通过。早期同机并发重载轮次完整准备约2.0～7.0秒；最新夹具的具体逐副本时间见bookworm-tls-fault-summary.json；20轮p50指标来自逐轮配对。生产并发延迟需单独按目标CPU配额验收。
