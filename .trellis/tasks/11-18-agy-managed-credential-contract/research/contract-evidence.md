# 凭据合同证据与实验矩阵

## 已核对的静态证据

- `services/gateway/src/model/account.rs:170`：现有 Account 定义 `access_token`、`refresh_token`、`expires_at`、账号身份及代理字段。AGY 平台与原生凭据字段由后续账号子任务设计。
- `services/gateway/src/service/native_runtime.rs:333`：WorkerIdentity 通过 NativeSubmission 取得 bearer 及身份。
- `services/gateway/src/service/native_runtime.rs:891`：CC 原生启动使用 `CLAUDE_CODE_OAUTH_TOKEN`。该入口仅作为 CC 参照。
- `services/gateway/src/service/gateway.rs:2942`：普通转发对未授权响应进入既有恢复路径，之后记录 oauth_recovery 并执行下一次实际发送。Google 错误分类待验证。
- `services/orchestrator/account_runtime.py:1238`：sync_credentials 在账号凭据锁内读取并发布 AT-only 副本，绑定账号移除 refreshToken。
- `services/orchestrator/test_credential_ownership.py:120`：既有测试覆盖交接、原账号保持、轮换、丢失回执与重启恢复。

## 规范入口与本轮关键合同

- `.trellis/spec/orchestrator/backend/account-runtime-v3.md:53` 至 83 行：受管凭据接口、完整身份核对、单一刷新所有者、活动许可覆盖实际网络发送、刷新前持久待确认以及未知结果对账。待办和证明表只保存归属与回执信息。
- `.trellis/spec/gateway/backend/service-architecture.md:839` 至 890 行：受信任管理端凭据解析；即使当前 AT 有效也获取账号刷新锁，获锁后及返回前读取权威账号；401 恢复有界，凭据和真实身份映射保持私有。
- `.trellis/spec/runtime/backend/runtime-contract.md:197` 至 207 行及 247 至 258 行：CC 原生发送、构造、终态及取消参照。AGY 实验须保留真实原生来源和出站证据。
- `.trellis/spec/gateway/backend/testing-quality.md`：测试只使用合成秘密，仓库报告只保留脱敏结果。修改产品源码时执行对应模块完整检查。

上述大规范按行段读取，避免整文件注入截断。合同的后续更新以原规范为准。

## 原生基线

- 本地原版：`/root/.local/state/agy-deployment/preserved/agy-1.5.9-original`。
- 本轮 SHA256 复核：`39816d49d5ab92229952987225c23ea3fed7580699dcb4a444e0388e0ac1ce43`。
- 脱敏材料：`/root/.local/state/agy-deployment/oauth-study/OAUTH_BASELINE.md` 与同目录 `baseline-evidence/{test-manifest,auth-validation,direct-generation-result,available-models}.json`。
- 原生文件相对账号 HOME 为 `.gemini/antigravity-cli/antigravity-oauth-token`。基线描述权限为 0600，包含 AT、RT 和到期时间。
- 基线已记录 consumer OAuth、新进程读取持久态及 gemini-3.8-flash-low 成功生成。文件内部字段和实时有效性以实验前私有核对为准。
- 旧压缩研究制品有独立 build-manifest，其身份与原版区别记录。该制品的重建差异待验证。

## 实验矩阵

| 场景 | 实验内容 | 证据与期望 |
| --- | --- | --- |
| V01 | 有效 AT、RT 缺省与空值 | 原生分别观察启动、目录、文本、额度和遥测；列出每项能力结论 |
| V02 | 过期 AT、缺有效期、坏文件及身份冲突 | 先以离线夹具验证受控失败及原文件保留，再记录原生实际约束 |
| V03 | 常驻进程读取后原子替换凭据 | 私有观察点关联出站代次，区分文件更新与进程实际采用 |
| V04 | 并发到期刷新 | 合成刷新服务与并发屏障验证单一所有者、一次有效刷新及原子保存 |
| V05 | 旧回执、RT 轮换与 CAS 竞争 | 注入交错回执，当前权威状态及新 RT 保持一致 |
| V06 | 刷新响应丢失、写入失败及重启 | 持久待确认并进入对账，恢复与原操作关联 |
| V07 | 真实认证失败前的恢复边界 | 离线验证有界恢复与原截止时间，原生 Google 错误分类单独记录 |
| V08 | SSE 已发送后凭据换代 | 已发送字节、实际尝试数、取消及终态逐项关联 |
| V09 | 工具等待与实际结果回填期间换代 | 真实进程、调用标识与临时文件效果计数保持关联 |
| V10 | 取消、退出、重新授权及停止排空 | 旧代控制与新代隔离，观察剩余进程、活动发送及遥测收尾 |

离线结果标记为夹具模拟。真实实验遵循 PRD 的账号环境及调用预算，无法覆盖的项目逐项标为待验证。

## 后续合同应交付的内容

- 原生支持的凭据结构、读取时机与更新入口，以及实测限制。
- 推荐的刷新所有者、发布代次和进程生命周期机制，附依据与恢复步骤。
- 认证恢复、SSE、工具等待和取消的实际边界。
- 账号、运行环境与请求记录所需关联信息和敏感字段边界。
