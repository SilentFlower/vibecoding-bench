# 升级 cc2api 到 2.1.197 - 技术设计

## 架构边界

本任务覆盖 `cc2api/` 子模块和 `vibecoding-bench` worker 默认版本配置。`cc2api` 仍按现有分层修改：版本画像集中在 `src/service/version_profile.rs`，请求重写在 `src/service/rewriter.rs` 与 `src/service/gateway.rs`，DB/settings 迁移在 `src/store/db.rs` 与 `src/store/settings_store.rs`，前端设置页在 `web/src/components/Settings.vue`。

## 版本画像

新增 `PROFILE_2_1_197`，并把默认常量切到该画像：

- `DEFAULT_CLAUDE_CODE_VERSION_PROFILE = "2.1.197"`。
- `DEFAULT_CLAUDE_CODE_VERSION = "2.1.197"`。
- `DEFAULT_CLAUDE_CODE_VERSION_BASE = "2.1.197"`。
- `DEFAULT_CLAUDE_CODE_BUILD_TIME = "2026-06-29T19:08:42Z"`。
- `DEFAULT_ALLOWED_CLAUDE_CODE_VERSIONS = "2.1.89-2.1.197"`。
- `stainless_runtime_version = "v26.3.0"`。

`2.1.195` 保留为内置回滚画像，`CLAUDE_CODE_PROFILES` 顺序改为 `2.1.197` 优先，其后保留 `2.1.195`、`2.1.187`、`2.1.185`、`2.1.173`。

## 请求协议

`2.1.197` 沿用 `2.1.195` 已验证的协议子画像：

- `STAINLESS_PACKAGE_VERSION = "0.94.0"`。
- `STAINLESS_RUNTIME_VERSION = "v26.3.0"`。
- `TelemetryShape::ClaudeCode2185`。
- `growthbook_user_agent = "Bun/1.4.0"`。
- `cc_version` 后缀沿用现有 SHA256 算法，多 text block 时取最后一个 user text block。
- CCH 使用 `CchProfile::ClaudeCode2172Plus`：seed 为 `0x4D659218E32A3268`；输入为最终 body 字节中将 `cch=<5hex>` 还原为 `cch=00000` 后，top-level `model` 字符串值置为 `""`，删除 top-level `max_tokens` 和 `fallbacks`。`diagnostics` 必须保留。远程 2.1.197 样本复算结果为 Haiku 1/1、Sonnet 5 66/66 命中。

Sonnet 5 主请求 beta 采用抓包顺序：

```text
claude-code-20250219,oauth-2025-04-20,context-1m-2025-08-07,interleaved-thinking-2025-05-14,redact-thinking-2026-02-12,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,mid-conversation-system-2026-04-07,advisor-tool-2026-03-01,advanced-tool-use-2025-11-20,effort-2025-11-24,extended-cache-ttl-2025-04-11,cache-diagnosis-2026-04-07
```

实现不把 `context-1m-2025-08-07` 放进通用必需 beta；仍由客户端传入 beta 与账号 `allow_1m_models` 共同决定。默认白名单改为 `"opus,claude-sonnet-5"`，所以 `claude-sonnet-5` 可透传 1M，`claude-sonnet-4-6` 继续过滤。

## 数据迁移

`src/store/db.rs` 的旧默认组合迁移需要加入：

- `DEFAULT_ALLOWED_CLAUDE_CODE_VERSIONS` 切到 `"2.1.89-2.1.197"`。
- `PREVIOUS_DEFAULT_CLAUDE_CODE_VERSION_PROFILE_SETTINGS` 增加 `"2.1.195"`。
- `ALTER TABLE accounts ADD COLUMN allow_1m_models ... DEFAULT`、新账号默认值和 serde 默认值改为 `"opus,claude-sonnet-5"`。

迁移策略遵守 settings/database 规范：只有 `claude_code_version_profile` 与 `allowed_claude_code_versions` 仍是旧默认组合时自动升级；管理员自定义过版本范围时保留显式配置。账号 `canonical_env` 在启动迁移中批量覆盖为当前 selected profile 的身份字段。

如果已有账号 `allow_1m_models` 仍是旧默认 `"opus"`，本任务需要在迁移中升级到 `"opus,claude-sonnet-5"`；管理员已自定义的值保持不变。该迁移同时考虑 SQLite 与 PostgreSQL。

## 前端与文档

前端账号编辑页的默认值、快捷按钮和说明同步为：

- 默认值：`opus,claude-sonnet-5`。
- 快捷项避免 `opus,sonnet`，改成“Opus + Sonnet 5”并写入精确值。
- 说明明确“逗号分隔子串，默认仅 Opus 与 Sonnet 5；不要用宽泛 `sonnet`，否则会影响 Sonnet 4.6”。

Settings 页内置 profile fallback 列表加入 `2.1.197`，默认 profile 与 allowed range 回显更新为 `2.1.197` / `2.1.89-2.1.197`。

`vibecoding-bench` worker Dockerfile、compose 默认 `CLAUDE_CODE_VERSION`、README 与 WebUI datalist 同步到 `2.1.197`。

## 回滚与部署

回滚可以通过管理后台切回 `2.1.195` profile，后端只接受内置 profile key。远程部署按 `cc2api.env` 规范执行：重启前检查 established 连接数，低连接窗口再 pull/recreate；部署后查 DB 版本分布和日志。

## 风险

- 1M 白名单仍是子串匹配，`claude-sonnet-5` 对未来 `claude-sonnet-5-*` 也会放行；这是当前配置机制的自然结果，但不会匹配 `claude-sonnet-4-6`。
- 当前远程样本没有 top-level `fallbacks`，`2.1.197` 对 `fallbacks` 的处理由二进制线索和既有 2172+ 规则推导；实现测试需要覆盖 top-level 裁剪只作用顶层字段，不误删嵌套 schema。
- 改默认 `allow_1m_models` 会影响老账号；迁移必须只改旧默认值，不能覆盖管理员显式自定义。
