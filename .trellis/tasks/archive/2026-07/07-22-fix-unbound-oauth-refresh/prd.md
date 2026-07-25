# 修复未绑定账号 OAuth 自动刷新

## Goal

修复未绑定 cc2api 的账号在 access token 临期或运行中遇到 401 时，因为刷新请求扩大 OAuth scope 而持续返回 `invalid_scope`、无法轮换 AT/RT 的问题，并让后台刷新失败具备脱敏、可持久查询的诊断信息。

## Background

- 线上账号 `7-19` 为 `enabled=1`、未绑定 cc2api、未开启养号，符合 `OAuthRefreshScheduler` 扫描条件；养号状态不参与 OAuth 刷新筛选。
- 线上调度器仍在每分钟运行，问题不是调度线程整体停止。
- 账号凭据实际只授权以下 scope：`user:profile`、`user:inference`、`user:sessions:claude_code`、`user:mcp_servers`、`user:file_upload`。
- 后台刷新和 worker 401 强刷都额外硬编码了 `user:design:read`、`user:design:write`。历史线上日志已明确记录 `HTTP 400 invalid_scope`，同类账号曾因此连续 159 次 `auth_failed`。
- Claude Code 2.1.197 自身成功刷新时使用原凭据的 5 个 scope；线上成功请求体比当前自定义刷新请求少 35 字节，恰好等于两个额外 design scope。
- 当前后台刷新异常在 `OAuthRefreshScheduler._tick()` 中被 `except Exception: pass` 静默吞掉，数据库、账号 API 和容器日志均无法判断最后一次尝试结果。

## Requirements

### R1. 刷新不得扩大授权 scope

- 未绑定账号的后台临期刷新和 worker 401 强制刷新必须使用凭据中已有的 `claudeAiOauth.scopes`。
- scope 必须只接受非空字符串并去重，保持稳定顺序。
- 凭据缺少或没有有效 `scopes` 时，刷新请求必须省略 `scope` 字段，让 OAuth 服务沿用原 grant；不得回退到包含新增权限的硬编码列表。
- 不得再无条件请求 `user:design:read` 或 `user:design:write`。
- 刷新成功后继续保存服务端返回的 scope；响应未返回 scope 时保留原凭据 scope，不得清空。

### R2. 保持现有刷新并发与网络契约

- 后台刷新仍只在 AT 缺失、无效、已过期或剩余不超过 10 分钟时触发。
- task 启动前不得新增强制刷新。
- 刷新仍必须在 worker → sidecar → 账号上游代理链路中使用 Node runtime 发起，`platform.claude.com` 保持 TLS passthrough，不得回退宿主网络。
- 同账号 RT 轮换仍由现有 owner/profile/file lock 串行化；并发 worker 的旧 RT `invalid_grant` 恢复语义保持不变。
- cc2api 绑定账号继续由 cc2api 独占 AT/RT 刷新，不进入本地 refresh 路径。

### R3. 后台刷新失败必须可诊断且不泄漏凭据

- 未绑定账号的后台刷新每次真实尝试后，持久记录最后尝试时间、结果和脱敏错误摘要。
- 状态至少区分 `success`、`failed`；未发生过尝试保持空值。
- 错误不得包含 access token、refresh token、Authorization、Cookie、代理密码或完整响应正文；只保留错误类别、HTTP 状态、`retry-after` 和服务端短错误码/短描述。
- 账号列表 API 返回安全状态字段，便于后续排查；本任务不要求新增复杂前端交互。
- 后台调度器遇到单账号刷新失败后必须继续扫描后续账号，不能让整个调度线程退出。

### R4. 回归测试

- 覆盖有 5 个既有 scope 时，两个刷新入口都只发送这 5 个 scope。
- 覆盖 scopes 缺失、空数组、混入空值/重复值时的省略或归一化行为。
- 覆盖刷新成功后 AT/RT/expiresAt/scopes 的写回语义。
- 覆盖 `invalid_scope`、`invalid_grant`、429 等失败的脱敏状态持久化，不泄漏 token。
- 覆盖绑定账号不调用本地刷新、未绑定账号临期时调用本地刷新、单账号失败不阻断后续账号。
- `bash -n images/worker/entrypoint.sh` 和 orchestrator 自动化测试必须通过。

## Acceptance Criteria

- [ ] AC1：代码中两条未绑定账号刷新路径不再硬编码或追加 `user:design:*`，请求 scope 与凭据已有授权一致；无有效 scope 时省略该字段。
- [ ] AC2：使用仅含 5 个历史 scope 的凭据 fixture 执行刷新测试，token endpoint 收到的 scope 不包含额外权限且刷新成功结果正确写回。
- [ ] AC3：后台刷新失败后，账号安全状态可查询，包含时间、结果和脱敏摘要，不包含任何 AT/RT/代理密码。
- [ ] AC4：一个账号刷新失败不会阻断后续账号扫描；cc2api 绑定账号行为不回归。
- [ ] AC5：相关单元测试、shell 语法检查和 Trellis 全量检查通过。
- [ ] AC6：发布对应 orchestrator/worker 镜像并在远程 force-recreate 后验证：调度器存活、账号状态接口正常、线上不再出现 `invalid_scope`。

## Out Of Scope

- 不改变 task 启动前不强刷 AT 的既有规则。
- 不修改 cc2api 的 OAuth 所有权和刷新实现。
- 不替账号 `7-17`、`7-19` 执行重授权，不主动轮换生产 RT 做破坏性验证。
- 不调整养号调度、账号并发数、代理配置或风控策略。
- 不在日志中输出完整 token endpoint 响应。
