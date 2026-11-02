# cc2api 账号禁止 Fast 时回落普通模式

## Goal

让 cc2api 账号关闭 Fast Mode 时，将客户端显式申请的 Fast 请求回落为普通模式，使禁止策略同时覆盖请求正文和配套 beta。

## Background

- 用户已确认采用“禁止时回落普通模式，允许时保留客户端申请”的行为，消息请求同时覆盖 API 与原生 Claude Code 来源。
- R13 合成链路发现：`allow_fast_mode=false` 已过滤 `fast-mode-2026-02-01`，但仍保留正文 `speed: "fast"`；见 `../10-29-cc2api-vm2api-wire-differential-study/research/round13/REPORT.md` 的 R13-01。
- 官方 Fast 文档当前允许 Opus 5.5 仅通过 `speed: "fast"` 申请 Fast；删旧 beta 不能完整表达禁止策略。公开 API 规则不能直接证明 OAuth 账号实际资格、速度或费用。
- `cc2api/src/model/account.rs:233` 已定义账号开关；当前正文路径位于 `cc2api/src/service/rewriter.rs:2146`，普通与状态分类分流位于 `cc2api/src/service/gateway.rs:2226`，count_tokens 独立入口位于同文件 `:1551`。

## Requirements

- **R1 禁止行为**：账号字段缺省或为 `false` 时，转发消息及 count_tokens 请求删除根级、精确值为字符串 `"fast"` 的 `speed`，并继续按完整 token 删除 Fast beta。回落普通模式，不新增请求拒绝或重试。
- **R2 允许行为**：账号字段为 `true` 时，本轮不改变正文的 Fast 申请；继续沿用已有 beta 策略，未请求 Fast 的客户端不会被主动开启。R13-02 的 API beta 丢失与自动补 beta 不在本轮范围。
- **R3 入口与账号一致性**：API、原生 Claude Code、流式及非流式请求使用同一账号策略；后台状态分类等转发分支不能绕过策略。换号后从原始逻辑正文按本次账号重新决定，不继承上一个账号的删减结果；count_tokens 认证恢复同样复用当前账号的正确正文。
- **R4 报文兼容**：只处理根级合法 Fast 申请，保留 `speed: "standard"`、其它值、嵌套同名字段及其它业务字段；无 Fast 删减时不引入额外正文序列化。遵循既有原生 280/293 画像、根级 CCH 定位、请求压缩重编码及最终长度生成规则。
- **R5 说明同步**：更新账号字段注释、Accounts 页面说明和 Fast 协议规范，明确禁止时回落普通模式。复用现有开关及默认值，保留 cc2api 为账号配置权威来源的约定。

## Acceptance Criteria

- [x] **AC1 → R1/R3**：API 与原生 CC 的 `speed: "fast"` 请求，在禁止账号上最终出站无根级 `speed` 和完整 Fast beta；覆盖入站有／无 beta、流式／非流式。
- [x] **AC2 → R2/R4**：允许账号保留 `speed: "fast"`；普通请求不新增 Fast，`standard`、异常值、嵌套 `speed` 和其它 beta 保持原有处理。
- [x] **AC3 → R3/R4**：状态分类分支与 count_tokens 通过实际 Gateway 验证；count_tokens 的专用 beta 及既有路由、认证恢复行为保留。
- [x] **AC4 → R3**：允许／禁止账号间换号时，每次出站均反映当前账号策略，不因前一次删减丢失客户端原始意图。
- [x] **AC5 → R4**：明文与现有支持的压缩编码在策略执行后得到一致逻辑 JSON，Content-Encoding 与实际字节一致，Content-Length 等于最终发送长度；已有合法 CCH 按最终逻辑正文校验，含 billing 透传模式。
- [x] **AC6 → R5**：页面说明、账号注释与协议契约一致，Rust 格式、必要单测与 Gateway 回归、完整 Rust 测试、CCH 检查和前端构建通过。

## Non-Goals

- 不处理 R13-02 的 API beta 合并、模型功能自动补 beta，也不改 VM。
- 不新增数据库列、设置项、模型映射、账号调度策略或前端控件。
- 不改变请求编码策略、缓存／统一 1h、响应内容、计费观测或版本画像。
- 不部署、不调用真实模型或账号，不承诺实际 Fast 速度、资格或费用结论。
