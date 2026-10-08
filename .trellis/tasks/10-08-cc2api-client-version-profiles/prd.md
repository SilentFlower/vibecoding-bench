# cc2api 按客户端版本同时适配 260 与 280

## Goal

让 cc2api 同时承载 Claude Code 2.1.260 与 2.1.280 客户端，按入站版本适配对应协议和遥测画像，默认以 2.1.280 为主，为后续经过抓包验证的版本保留扩展入口。

## Background

- 用户要求先实现 260/280 双版本适配，293 由用户另行抓包。
- 用户明确：缺少 UA 版本时直接使用默认画像，不从请求体补充识别客户端版本。
- 两版画像和脱敏签名 fixture 已存在，见 `cc2api/src/service/version_profile.rs:633`、`:683` 和 `cc2api/tests/fixtures/claude-code-2.1.260-profile.json`、`claude-code-2.1.280-profile.json`。
- header/body 与 bootstrap 从账号 canonical env 选择画像，见 `cc2api/src/service/rewriter.rs:1342`、`:1939`、`cc2api/src/service/gateway.rs:2707`。
- 全局画像切换事务更新所有账号 env 与允许版本范围，见 `cc2api/src/store/settings_store.rs:180`。
- 自动遥测只按账号保存状态，续期覆盖账号副本，后台 UA 又读取持久账号版本，见 `cc2api/src/service/telemetry.rs:334`、`:355`、`:598`。
- 保留创建任务时已有的 `.trellis/spec/vibecoding-bench/deploy/official-protocol-capture.md` 改动；开发阶段保留父仓 cc2api 子模块指针，后续 Git 交付按用户确认的计划更新到本次新提交。

## Requirements

- R1：客户端版本适配模式下，仅使用原始 Claude Code/CLI UA 识别客户端版本，明确声明 2.1.260 或 2.1.280 时分别使用对应内置画像；同一请求的账号切换、401 恢复与签名重试保持选择结果一致。
- R2：普通 API、缺少 UA 版本、非法 UA 版本与本轮未支持的版本使用管理员配置的默认画像，出厂默认仍为 280；请求体中的版本字段不参与选择。现有访问策略先行生效，画像回退不放行被拒绝请求。
- R3：所选版本贯穿 header、body、模型和辅助请求子画像、billing/CCH、bootstrap、hello 探测、原生遥测与自动遥测，不只改变版本字符串。
- R4：同一账号可以承载两版客户端；请求适配不写入 canonical env，不改变凭证、device_id、账号 UUID、代理、硬件或操作系统身份。
- R5：自动遥测、stateful 消息缓存、hello 探测与非流式探针缓存按有效画像隔离，异步响应、续期和后台发送不被另一版本覆盖；管理 API 保持账号级聚合。
- R6：真实 session 的 sticky、RPM、并发与上游 session 池保持原契约，版本隔离不扩大账号容量。
- R7：新增选择方式设置，默认按客户端版本适配，可切回原账号画像方式；已有默认画像选项和管理员显式配置保留。

## Acceptance Criteria

- [x] A1 / R1、R3：同账号交错的 260/280 请求，其出站 UA、Stainless、beta、body、billing 后缀和 CCH 均符合对应画像。
- [x] A2 / R1、R2、R7：默认 280、UA 精确识别、UA 缺失/非法/未匹配版本回退、请求体版本不参与选择、访问拒绝、设置非法值和热刷新有覆盖；旧模式按账号画像运行。
- [x] A3 / R4、R6：请求前后持久身份不变，调度、sticky、RPM、并发与上游 session 池既有回归通过。
- [x] A4 / R3、R5：bootstrap、hello、原生与自动遥测跟随有效画像；交错激活、同秒运行 ID、延迟结果、UA/payload 与账号级聚合正确。
- [x] A5 / R5：同账号同真实 session 的不同版本不共用版本相关缓存；延迟提交不覆盖另一版本。
- [x] A6 / R1、R3：使用现有 fixture 覆盖 CCH、嵌套 model、fallbacks、工具结果和线程续轮，未知字段/SSE 保真。
- [x] A7 / R3、R7：`cargo fmt --check`、完整 `cargo test`、`cargo test cch` 和设置页 `npm run build` 通过。

## Out of Scope

- 293 新画像、真实抓包、生产推理、部署和发布。
- 开发阶段不提交或推送；实现、检查及规范同步后，用户另行确认双仓提交、推送与任务完成记录计划，Git 交付纳入此次授权。
- vm2api 槽内 CLI 架构、账号设备身份分裂、重新推导现有 260/280 算法。
- 从 Bun/axios/Stainless 版本猜测 Claude Code 版本，或为未验证版本拼装画像。
