# cc2api 访问策略错误体兼容 new-api

## Implementation Checklist

- [x] 阅读 cc2api 访问策略响应和现有错误响应实现。
- [x] 将 `access_policy_error_response` 的 `error` 字段改为对象格式。
- [x] 保留 `setting` 和 `reason` 顶层字段，便于 cc2api 日志/调用方排查。
- [x] 将 `system_role_model_error_response` 的 `error` 字段改为对象格式。
- [x] 保留 `model` 和 `allowed_system_role_models` 顶层字段。
- [x] 更新访问策略相关单测，断言 `type`、`error.type`、`error.message`、`setting`。
- [x] 更新 system role 相关单测，断言 `type`、`error.type`、`error.message`、`error.code`。
- [x] 执行验证命令。
- [ ] 提交并 push `cc2api`，再按需提交父仓 Trellis 任务记录。

## Validation

- `docker run --rm -v /root/project/cc2api:/app -v /root/.cargo/registry:/usr/local/cargo/registry -v /root/.cargo/git:/usr/local/cargo/git -w /app rust:1.86-bookworm cargo test --offline access_policy`
- 可行时执行 `docker run --rm -v /root/project/cc2api:/app -v /root/.cargo/registry:/usr/local/cargo/registry -v /root/.cargo/git:/usr/local/cargo/git -w /app rust:1.86-bookworm cargo check --offline`
- `git diff --check`

已执行：

- `docker run --rm -v /root/project/cc2api:/app -v /root/.cargo/registry:/usr/local/cargo/registry -v /root/.cargo/git:/usr/local/cargo/git -w /app rust:1.86-bookworm cargo test --offline access_policy`：通过，6 个相关单测通过。
- `docker run --rm -v /root/project/cc2api:/app -v /root/.cargo/registry:/usr/local/cargo/registry -v /root/.cargo/git:/usr/local/cargo/git -w /app rust:1.86-bookworm cargo test --offline system_role`：通过，3 个相关单测通过。
- `docker run --rm -v /root/project/cc2api:/app -v /root/.cargo/registry:/usr/local/cargo/registry -v /root/.cargo/git:/usr/local/cargo/git -w /app rust:1.86-bookworm cargo check --offline`：通过。
- `git diff --check`：通过。

## Review Gates

- HTTP status 仍为 403。
- `error` 必须是对象，不能再是字符串。
- message 不包含 token、请求体或上游敏感信息。
- 不改变访问策略匹配语义。
- 不改变 system role 模型白名单语义。
- 不改变上游错误透传和 account busy / 429 行为。

## Check All Result

- 三件套实现：通过。PRD 要求的 access policy 403 和 system role 400 均已改为 `{"type":"error","error":{"type":"invalid_request_error","message":"...","code":"..."}}`，并保留原诊断字段。
- 假设验证：通过。new-api `RelayErrorHandler` 对 `error` 对象会解析 `message`；本任务没有修改上游透传、429 account busy、状态码映射或访问策略匹配逻辑。
- 跨层完整+规范：通过。改动只在 cc2api 服务层本地错误响应，未涉及 DB/UI；新增/更新单测覆盖两个本地拒绝响应 schema。
- Spec 更新：不需要。该知识属于 cc2api 与 new-api 兼容的任务级实现，不适合写入当前 vibecoding-bench 项目规范。
