# 请求记录任务实施清单

## 开工前提

- [x] 依赖任务已完成，父需求与现有UI接入原则明确。
- [x] 已读取实际诊断DTO、存储、Gemini后台执行、工具归属及采集读取合同。
- [x] 已明确零真实模型费用、隔离数据库及生产操作边界。
- [x] 三件套收敛、完整Brief评审通过后启动任务。

## 执行顺序

1. 为当前网关产物保留隔离旧程序验证副本；落实追加schema定义、登记版本6、执行/验证分支、SQL投影及双库迁移测试。冻结原步骤，验证旧程序compatible_newer。
2. 扩展显式DTO及DiagnosticsStore查询/计数、历史未知筛选和限定工具状态更新；对照所有struct字面量与管理投影，保留终态防回退和16KiB摘要预算。
3. 将AGY已鉴权HTTP接入现有根记录；建立协议专用attempt观察，显式跨spawn传归属。接通准备拒绝、真实提交、401恢复、源用量、取消与控制终态。
4. 关联工具前驱根/attempt与原native状态，验证同HTTP恢复、跨HTTP新快照、原轮晚收口及超时；诊断故障保持模型、工具和许可语义。
5. 建立AGY独立有界脱敏快照，复用入口脱敏和既有管理读取，补独立采集旁路、平台归属校验及统一容量/保留清理；失败仅记录采集缺口。
6. 更新前端DTO、全平台账号选项和既有请求筛选/四页签；验证历史缺字段、真实0、长模型、来源标签、390px与迟到回执。
7. 执行下方场景和对应自动化；完成Check-All、Spec及精确Push计划。父任务跨子项最终状态核对由后续父任务收尾承接。

## 场景—路径—期望

| 场景 | 路径 | 核心期望 |
| --- | --- | --- |
| CC历史/新请求 | 迁移→管理列表/详情→既有发送 | 原字段与采集兼容，新字段未知明确 |
| AGY普通/SSE/AGY上Claude | 公共HTTP→真实SQLite→原生本地TLS→管理页 | 每HTTP一根，平台/协议/模型正确 |
| 准备拒绝和提交未知 | 原边界故障→存储/查询 | 0或实际提交次数准确，阶段与未知可见 |
| 401/凭据刷新 | 一根两尝试→管理链路 | 原代/新代、原因及策略快照对应 |
| 工具往返/换代 | 首轮HTTP→真实MCP回填→后续HTTP | 前驱关联、原工具收口及原HTTP结果保持 |
| 取消/截断/容量/截止 | 已交付流或控制失败→真实idle | 有界终态、部分用量及原许可释放 |
| 策略变化 | 账号A/B、开启/关闭/幂等→实际TLS/管理策略 | 账号隔离、冻结与实际changed一致 |
| 权限与采集 | info/debug/关闭/过期/越界/链接/超限 | 脱敏、来源/截断、no-store及归属正确 |
| 筛选与移动端 | 组合筛选→服务端计数/分页→390px | 数据集一致，草稿/焦点/迟到隔离 |
| 诊断故障 | 队列满/写入失败/采集404或超时 | 缺口可见，业务提交和响应保持 |

## 验证计划

按实际影响执行并记录退出状态，复用未变化且仍覆盖当前范围的证据：

```bash
cargo fmt --check --manifest-path services/gateway/Cargo.toml
cargo test --locked --manifest-path services/gateway/Cargo.toml
PYTHONPATH=services/orchestrator:deploy/flower2api /root/project/vibecoding-bench/.venv/bin/python -m unittest test_agy_runtime test_agy_supervisor test_agy_system_prompt test_native_capture
PYTHONPATH=services/orchestrator:deploy/flower2api /root/project/vibecoding-bench/.venv/bin/python -m unittest discover -s deploy/flower2api
npm --prefix apps/web run build
```

- 显式运行隔离PostgreSQL诊断存储与迁移测试；ignored状态不计通过。SQLite验证升级、重开、重复及旧程序读写，PG验证NULL/实值往返及查询。
- 扩展verify_agy_gemini.py及verify_agy_native_loopback.py；原生使用明确镜像、UID1001、network=none、本地TLS与合成身份，外部模型提交0。
- 扩展实际构建产物浏览器探针，覆盖UI/API/DB对应场景及既有CC回归；执行时按全链路技能加载场景和数据恢复细则。
- 新增采集内部路由、读写和清理测试覆盖固定归属、敏感值重复引用、截断、旧组件缺口与失败不重放。
- 编排全量回归按最终影响面补跑；既有python-dateutil种子摘要错误与本任务证据分别登记。

## 预计文件责任与回退

gateway：request_diagnostics DTO、diagnostics观察、gemini接线、diagnostics_store、router/runtime_bridge、AGY快照/传输及追加迁移模块与登记。orchestrator：AGY事件/采集快照、受信读取发布与清理。web：api.ts、RequestDiagnostics.vue、账号选择器的全平台请求选项及必要样式。deploy：签发来源映射与隔离回归探针。其他父任务、集群工作及new-api保持独立归属。

诊断旁路开关/缺口不改变原模型链路。已保存数据与当前权威账号凭据保留；兼容旧程序回退须经隔离读写证明。生产迁移、发布及真实账号验收另行授权。
