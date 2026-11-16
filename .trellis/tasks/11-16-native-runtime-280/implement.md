# 实施与验证计划

## 实施顺序

1. [x] 读取受影响包规范、实体/DTO、运行时入口、构建与测试定义。固定官方280文件及实际Bun身份，提取并记录模块、原生请求接口与资源布局；使用隔离HOME和网络。
2. [x] 增加280专属适配与构建配方，运行原版280回环矩阵，再对精简候选运行相同矩阵及独立部署验收。登记来源、分发/执行体身份及实际体积与时延。
3. [x] 扩展版本选择、私有信封、准备及诊断合同，接入既有冻结画像。保留历史信封293缺省及原始账号的调度/凭据所有权。
4. [x] 改造sender为账号统一容量与版本化子状态，覆盖映像/进程/补位/模板/清理。加入两版交错、并发、取消、热刷新及旧身份失效测试。
5. [x] 同步Python编排、签名清单核验、安装路径、镜像构建、版本化升级与回退。独立评估280恢复/TLS能力，确保实际执行体和版本匹配。CI沿固定npm来源和已有构建配方生成280制品，缓存仍按最终摘要验证；本地构建继续支持显式制品路径。
6. [x] 更新账号原生后端文案及各版准备/诊断状态，覆盖部分就绪、失败、旧响应兼容与迟到结果。
7. [x] 完成跨层合成回环、目标包检查、Check-All、规范评估与精确Git计划。

## 验证入口

- runtime：在 `services/runtime` 执行 `bun run typecheck`、`bun test tests/unit`、`bun run test:integration`；按已读取的原生夹具定义执行280原版、280候选及293回归。验证入口涉及固定摘要时先适配版本参数与断言，再执行。
- 构建准入：同配方重复构建核对摘要，验证错误源/布局/超预算失败；独立部署回环、真实TLS CCH独立复算、Unicode、工具/thinking、原始响应、取消、单次发送及多轮隔离。
- gateway：在 `services/gateway` 执行 `cargo fmt --check`、`cargo check --locked`；按实际测试名称执行版本选择、native_runtime、native_prewarm、native_release与runtime_transport相关用例。后续Check-All补齐该层规范要求的检查。
- orchestrator：在 `services/orchestrator` 执行 `python3 -m unittest test_native_sender test_native_kernel_upgrade test_native_kernel_releases test_account_runtime`，并运行新增的双版本、预算及恢复合同用例。
- 前端：读取 `apps/web/package.json` 后选择其真实类型/构建命令；沿现有原生环境浏览器夹具验证自动选择文案、280/293状态、旧接口、明暗及390/1280px。
- 集成：合成凭据和本地TLS接收端覆盖同账号280/293顺序/并发请求，核对实际执行体、最终正文版本、metadata/billing/CCH、账号总容量；注入缺制品、错签名/版本/执行体、恢复失败、升级取消和旧回执。

## 重点文件与回退点

- `services/runtime/src/runtime/293/*`、`src/shared/native-input.ts`、构建/签名/验收脚本：保持293已验证路径及摘要绑定。
- `services/gateway/src/service/{gateway,native_contract,native_runtime,native_release,native_criu,native_prewarm,runtime_transport}.rs`：确保版本选择冻结、账号总容量、唯一投递和物理退出归还。
- `services/orchestrator/{native_sender,native_kernel_upgrade,native_kernel_releases,account_runtime}.py`及镜像输入：同步安装和协议版本，升级/回退按版本隔离。
- 账号和环境前端及私有状态消费者：同步字段，保持旧响应兼容和只读检查零唤醒。

## 实施门禁

- 首次实施按 `trellis-task-brief` 完整展示交接并取得适用授权，再执行 `task.py start` 与 `trellis-route`。
- 技术未知先通过源码研究和隔离实验解决；涉及范围或验收变化时先同步材料并确认新增决策。
- 280完成独立准入后才进入消费接纳表；最终交付以端到端自动选择验收为准。

## 本地生成与提交依赖

采集器canonical要求已提交且路径干净，镜像正式清单引用该真实revision。当前开发快照已用于隔离镜像验收。精确Git计划采用以下顺序：

1. 先提交本任务涉及的 `services/runtime/native/tls-observer/{observer.py,verify_container.py,verify_sender.py,README.md}`。
2. 在 `services/runtime` 执行已有稳定入口：`python3 native/tls-observer/export_bundle.py --output /root/project/vibecoding-bench/images/v3/tls-observer --control-policy-output /root/project/vibecoding-bench/services/orchestrator/native_tls_seccomp.json`。
3. 核对正式清单development=false、真实source_revision及每个文件摘要。预期变化仅 `images/v3/tls-observer/{observer.py,manifest.json}`；seccomp保持同字节。
4. 提交余下本任务代码与规范，并推送精确计划，再由任务进度所有者同步记录。

该顺序在Push阶段展示并等待适用授权。前置提交及正式导出属于Git交付链的确定性步骤。
