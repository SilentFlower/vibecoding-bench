# 为 cc2api 增加 Claude Fast Mode 可配置控制

## Goal

阻止下游 Claude Code 客户端自行通过 `anthropic-beta: fast-mode-2026-02-01` 开启上游 Fast Mode，同时为管理员保留明确、可持久化的放行能力，避免 Fast Mode 引发额外计费或 429 风险。

## Background

- 当前 `cc2api` 的 Claude Code 通用 beta 画像不会主动注入 `fast-mode-2026-02-01`。
- `src/service/rewriter.rs` 目前只对 `context-1m-2025-08-07` 做账号白名单过滤；其他客户端传入 beta 会通过 `merge_anthropic_beta` 合并进入最终上游请求。
- 因此客户端显式携带 `fast-mode-2026-02-01` 时，当前实现会将其透传给 Anthropic 上游。
- 现有 `allow_1m_models` 已提供账号字段、数据库迁移、管理 API、前端账号表单和请求重写的完整跨层模式，可作为本功能的实现参照。
- 对历史会话执行 `trellis mem` 检索未找到已确认的 Fast Mode 产品决策。

## Requirements

- R1：默认禁止客户端开启 Claude Fast Mode；新账号和迁移后的旧账号都不得默认透传 `fast-mode-2026-02-01`。
- R2：采用账号级布尔配置 `allow_fast_mode`；默认值为 `false`。管理员可以显式设置为 `true`，决定目标账号是否允许透传 Fast Mode；客户端自身不能覆盖管理员配置。
- R3：过滤必须按逗号分隔的完整 beta token 精确匹配，保留其他 beta token 的原始相对顺序，不能使用子串替换。
- R4：`/v1/messages` 与 `/v1/messages/count_tokens` 等会合并客户端 beta 的路径必须采用一致策略；要求精确画像、不会合并客户端 beta 的特殊请求保持现有行为。
- R5：配置必须完整贯穿 `Account`、SQLite/PostgreSQL 兼容迁移、账号 Store、创建/更新 API、前端 `Account` 类型和账号编辑表单。
- R6：功能不得改变 `context-1m-2025-08-07` 的现有白名单语义，不得改变默认 Claude Code 版本画像、CCH 或 `cc_version` 的计算规则。
- R7：协议重写必须发生在最终上游 header 生成及相关 CCH/计费画像计算之前。
- R8：`vibecoding-bench` 首次同步并创建 cc2api 账号时，创建 payload 必须显式发送 `allow_fast_mode: false`，不能只依赖 cc2api 服务端默认值。
- R9：`vibecoding-bench` 同步到已存在或已绑定的 cc2api 账号时，只校验身份、绑定并同步凭据，不得覆盖该账号已有的 `allow_fast_mode` 管理员配置。

## Acceptance Criteria

- [ ] AC1：默认配置下，客户端请求包含 `fast-mode-2026-02-01` 时，最终上游 `anthropic-beta` 不包含该 token，其他 beta 保持存在且顺序稳定。
- [ ] AC2：管理员显式允许后，同一请求的最终上游 `anthropic-beta` 保留 `fast-mode-2026-02-01`。
- [ ] AC3：未携带 Fast Mode beta 的请求不发生无关 header 变化。
- [ ] AC4：新账号默认禁止 Fast Mode；旧数据库迁移后默认禁止；配置创建、读取、更新和账号列表返回可以正确往返。
- [ ] AC5：账号管理 UI 可以查看和修改配置，默认状态清晰表达为禁止客户端 Fast Mode。
- [ ] AC6：`cargo fmt --check`、相关 Rust 单测、`cargo test cch` 和 `web` 构建通过。
- [ ] AC7：bench 首次同步创建账号的回归测试断言创建 payload 包含 `allow_fast_mode: false`，同步成功并正确写入 `cc2api_account_id`。
- [ ] AC8：bench 匹配既有账号和重复同步时不调用账号创建或配置更新接口，既有 Fast Mode 配置不会被同步流程重置。
- [ ] AC9：`python3 -m unittest orchestrator/test_main.py` 通过。

## Out Of Scope

- 不实现通用的任意 `anthropic-beta` 规则引擎。
- 不主动给任何请求注入 Fast Mode beta。
- 不调整 Anthropic 上游 Fast Mode 的计费、限流或账号调度逻辑。
- 不在 bench 数据库复制保存 `allow_fast_mode`；该配置的唯一权威来源仍是 cc2api 账号。
