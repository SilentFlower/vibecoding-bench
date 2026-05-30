# Run 可靠性：思考预算配置、超时收尾、OAuth 401 恢复

## Goal

提升批量 run 的自动完成率，减少因过度思考、长时间调研、工具失败恢复不当、OAuth access token 刷新竞态导致的 `timeout`。本任务应让思考预算可配置，默认从 `max` 调整为 `xhigh`，并让运行中的 token 更新和 401 场景能快速恢复或明确失败，而不是一路等到任务超时。

## Background / Known Context

- 远程 5 个 run (`46a9e72ed5eb`, `a4ded70d095f`, `17e64e4f6b22`, `c9385c530dbe`, `038e18dac0cf`) 均为 `status=timeout`、`exit_code=124`，任务 `timeout_sec=3000`，实际运行约 3035-3038 秒。
- 已观察到这些 run 的 `/v1/messages` 响应基本为 HTTP 200，没有 429/5xx；主要问题不是远端 API 故障，而是 Claude Code 没在 deadline 前产出最终 assistant 文本。
- 典型失败形态包括：过长环境调研、安装依赖/验证耗时、并行工具调用失败后没有恢复、后台安装失败后长时间停滞。
- 当前默认思考配置在 `orchestrator/main.py` 和 `images/worker/entrypoint.sh` 中硬编码为 `CLAUDE_CODE_EFFORT_LEVEL=max`，不是用户可配置项。
- Claude Code 官方文档支持 `CLAUDE_CODE_EFFORT_LEVEL`；`settings.effortLevel` 支持 `low|medium|high|xhigh`。本任务默认使用 `xhigh`，保留通过环境变量覆盖的能力。
- 当前 OAuth 后台刷新器每 60 秒检查账号 profile，10 分钟内过期则用临时 worker 刷新 token，并原子回写 `data/profiles/<account>/.credentials.json`。
- 当前 task worker 启动时把 profile 拷贝进 run 私有 `.claude-home`；如果后台刷新器在 run 运行期间更新了 profile，正在运行的 worker 不会自动拿到新 access token。
- 用户明确要求：不要做“启动 run 前强制刷新账号 token”。本任务只处理运行中遇到定时刷新或 401 的竞态；遇到刷新窗口时不能死等到 timeout。

## Requirements

- 思考预算必须可配置：
  - 默认值改为 `xhigh`。
  - 支持通过 `.env` / compose 环境变量调整。
  - worker 写入 Claude settings 时必须使用该配置，而不是硬编码 `max`。
- 批量任务和单任务的 prompt 必须增加自动跑题约束：
  - 优先最小可运行 MVP。
  - 避免长时间环境调研和非必要大型依赖安装。
  - 验证失败时允许降级到轻量验证并收尾。
  - 临近超时时必须停止扩展功能并输出最终总结。
- worker 必须支持临近超时自动收尾：
  - 在 deadline 前一个可配置窗口内，向 Claude TUI 注入一次简短收尾指令。
  - 注入必须最多一次，不能重复打断。
  - 若随后出现最终 assistant 文本，按 success 处理；否则仍按 timeout 处理。
- 运行中 OAuth token 同步必须可恢复：
  - 不做 run 启动前同步强刷。
  - 当后台刷新器更新账号 profile 的 `.credentials.json` 后，正在运行的 worker 应能把新 credentials 同步到本地 `$HOME/.claude/.credentials.json`。
  - 同步应使用原子替换，避免 Claude Code 读到半写入文件。
  - run 结束时不得把旧 credentials 回写覆盖 profile。
- 401 场景必须快速处理：
  - worker 或 sidecar 检测到 Claude Code 对 Anthropic/Claude API 返回 401 时，不能继续静默等待到 timeout。
  - 若 profile 中已有更新后的 credentials，应快速同步到 worker 本地，并给 Claude TUI 一次重试/继续提示。
  - 若短时间内仍无法恢复，应将 run 标为明确的认证失败状态或写入明确错误，不应伪装成普通 timeout。
- WebUI / 状态展示应能区分认证失败：
  - 至少在 run `error` 中包含可见的 OAuth/401 失败原因。
  - 如新增 `auth_failed` 终态，前端 legend、pill、终态判断需同步更新。

## Acceptance Criteria

- [ ] `.env.example` 和两个 compose 文件暴露 `CLAUDE_CODE_EFFORT_LEVEL`，默认 `xhigh`。
- [ ] `orchestrator/main.py` 与 `images/worker/entrypoint.sh` 不再硬编码 `CLAUDE_CODE_EFFORT_LEVEL=max` 作为唯一来源。
- [ ] 新创建任务和批次生成的 prompt 包含自动收尾/降级验证约束。
- [ ] worker 在临近超时窗口只注入一次中文收尾提示，并保留原有最终 assistant JSONL 判定。
- [ ] 运行中的 worker 能从挂载的账号 profile 同步刷新后的 `.credentials.json` 到本地 Claude home，且使用原子替换。
- [ ] 运行中出现 401 时，系统会尝试同步新 credentials 并重试/继续；无法恢复时记录清晰的 OAuth/401 失败，不再纯等到 timeout。
- [ ] 若新增状态，`_TERMINAL_RUN_STATUSES`、批次 done 统计、WebUI run legend/action/pill 均同步处理。
- [ ] 不实现“启动 run 前强制刷新账号 token”。
- [ ] 本地语法检查通过；能构建相关镜像或至少能运行可替代的静态/语法验证。

## Definition of Done

- 代码改动符合现有 FastAPI 单文件、静态 WebUI、worker shell 脚本风格。
- 所有新增用户可见文案、注释、文档使用中文。
- 运行路径不泄漏 access token、refresh token、账号密码或 prompt 敏感内容。
- 清理路径继续吞异常，主流程状态更新使用 `_db_lock`。
- 更新部署说明或 `.env.example`，让远程实例可通过 `.env` 改思考预算。

## Out of Scope

- 不实现启动 run 前强制刷新账号 token。
- 不重写调度器或引入队列系统。
- 不把现有人工“继续”机制改造成完整自动 retry 产品。
- 不引入 ORM、前端框架、构建链或新的复杂依赖。
- 不修复已经完成的历史 run 状态；历史 run 只作为根因样本。

## Research References

- `research/claude-code-effort.md`
- `research/run-timeout-oauth-findings.md`
