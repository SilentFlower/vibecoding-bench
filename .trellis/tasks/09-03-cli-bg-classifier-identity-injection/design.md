# 技术设计

## Architecture

本次只修改 `cc2api`，在现有窄 detector 旁增加通用 detector，并把后台分类配置收敛为一个内存配置快照：

```text
downstream /v1/messages
  -> client type / parsed body
  -> existing narrow detector
       -> mode=mock: local response
       -> mode=passthrough: retain current minimal bypass eligibility
  -> generic classifier detector
       -> mode=passthrough
       -> identity_injection_enabled=true
       -> non-Haiku
            -> metadata/session rewrite
            -> create or retain billing block
            -> insert identity block when missing
            -> compute or refresh CCH
            -> summary-only capture
  -> otherwise current normal rewrite path
```

现有 mode detector 与新 generic detector 分责，避免“修复真实透传”意外扩大本地模拟范围。

## Setting Contract

新增 setting：

- key: `intercept_cli_bg_status_classifier_identity_injection_enabled`
- values: `true | false`
- default: `false`
- effective condition: `mode=passthrough` 且通用 classifier 命中

后端使用：

```rust
struct CliBgStatusClassifierConfig {
    mode: CliBgStatusClassifierMode,
    identity_injection_enabled: bool,
}
```

以单个 `RwLock<CliBgStatusClassifierConfig>` 替换只保存 mode 的锁，保证 mode 与 injection 开关在一次热路径读取中保持一致。`reload_cli_bg_status_classifier_config()` 同时加载两个 setting；启动加载和管理 API 更新都调用同一入口。

同步位置：

- `src/store/settings_store.rs`: 默认常量。
- `src/store/db.rs`: 默认插入和迁移保护测试。
- `src/handler/router.rs`: GET 默认、布尔校验、保存后热刷新及 API 测试。
- `src/main.rs`: 启动加载。
- `src/service/gateway.rs`: 配置结构、内存锁、reload、测试 accessor、热路径读取。
- `web/src/components/Settings.vue`: ref、加载、保存、独立 checkbox 和说明。

`web/src/api.ts` 已使用 `SettingsMap=Record<string,string>`，预计无需新增 DTO；实现前仍需核对现有定义。

## Detection Contracts

### Existing Narrow Detector

保留当前 `is_cli_bg_status_classifier_request` 的事故画像语义，必要时改名为 `is_known_cli_bg_fable_status_classifier_request`，继续服务：

- `mock` 提前返回。
- 当前 Fable 5.1 passthrough identity-only 旁路。
- 原有日志、probe cache 排除和重试边界。

其精确模型、`x-app=cli-bg`、`max_tokens=3072` 等限制不作为新身份注入的通用依据。

### Generic Identity-Injection Detector

新增 `is_claude_code_status_classifier_request`，按结构化 JSON 逐层判断：

1. path/client: `/v1/messages` + `ClientType::ClaudeCode`。
2. surface: 原始 `x-app` 只接受 `cli` 或 `cli-bg`。
3. stream: `true` 排除，`false` 或缺失接受；其他类型排除。
4. system: 数组中恰好一个 classifier block；其余 block 只能是最多一个 billing 和最多一个精确 identity，重复块直接排除。
5. classifier markers: 用多个稳定语义片段和 schema 字段联合判断，不依赖完整字符串或 hash。
6. messages: 唯一 user 消息、唯一 text 内容，并包含四个输入标签。

返回结构可包含后续决策所需摘要，避免多次扫描：

```rust
struct CliStatusClassifierMatch {
    model: String,
    has_billing: bool,
    has_cch: bool,
    has_identity: bool,
}
```

若借用生命周期会令 Gateway 分支明显复杂，可返回轻量布尔并用小型纯函数读取上述字段；不为一次判断引入跨模块抽象。

## Injection And Body Rewrite

扩展现有 `rewrite_claude_code_identity_only`，增加明确的前缀补齐选项，或新增职责窄的包装方法。实现必须先复用现有 metadata/session 映射，再修改 system：

1. 解析 JSON，失败则返回原 bytes。
2. 更新 `metadata.user_id` 与 upstream session。
3. 若缺少 billing，复用 API 模式现有 billing builder，按所选账号 Claude Code 版本画像和当前请求上下文生成带 CCH 占位的标准 billing block；不得执行 API 模式的 expansion 注入。
4. 若缺少精确 identity，插入固定身份块；已有 identity 保持单份。
5. 仅对 detector 已确认的三种允许块重建 system 顺序为 billing、identity、classifier，不触碰各块内部字段。
6. 序列化 JSON，并在最终正文上处理 CCH：新建 billing 时生成有效 CCH；已有 billing 且含 `cch=` 时刷新；已有 billing 但无 `cch=` 时保持原样。

identity block 固定为：

```json
{"type":"text","text":"You are Claude Code, Anthropic's official CLI for Claude."}
```

不得添加 expansion、cache_control、TTL 或其他 system 内容。

## CCH Rationale

2.1.257 的 CCH 输入包含序列化后的正文，并对 model/max_tokens/fallbacks 做画像相关规整。插入 system block 会改变 CCH 输入；若保留原值，上游可能把正确身份修复再次判为画像不一致。

因此缺少 billing 时应复用 API 模式的标准 billing 构造入口，并在最终序列化后生成有效 CCH；已有 billing 且包含 CCH 时调用现有 `refresh_cch_attestation`。已有 billing 但不含 CCH 时保持其历史格式。整个分支不得重新执行完整 system 环境改写，也不得加入 expansion。

## Gateway Decision Order

在账号选择前完成两个 detector 的只读判断并取得一次配置快照：

- narrow + mock：沿用当前提前返回。
- generic + passthrough + injection enabled + non-Haiku：优先启用“身份映射 + billing/identity 补齐 + CCH compute/refresh”旁路；即使同时命中 narrow，也不能被旧旁路提前截走。
- narrow + passthrough 且未进入上一分支：沿用当前最小正文改写旁路，保证开关关闭时行为不变。
- 其余情况：沿用当前普通改写路径。

注入命中必须使用 `SummaryOnly`，并跳过 non-stream probe cache，避免缓存未注入/已注入的不同出站正文。

## UI

在现有“Claude Code 后台状态分类”区域保留两个 radio：

- 透传
- 模拟

下方增加独立 checkbox：

- 关闭文案：`保持原始身份块`
- 开启文案：`缺失时注入身份块`

说明文案必须明确：开启后仅对命中的非 Haiku classifier 生效，并会同时补齐缺失的 billing/CCH 归因块；这仍是一个独立开关，不增加第三个配置项。

当 mode 为 `mock` 时控件可以保持已保存状态，但以 disabled 样式呈现，旁边只说明“模拟模式不访问上游”。切回 passthrough 后立即恢复原保存值的可编辑状态。

## Compatibility And Rollback

- 数据库默认 false，升级后行为不变。
- mode key、枚举值和现有 mock 协议不变。
- 快速回滚只需关闭 identity injection；billing/CCH 补齐随同关闭，无需切换 mock。
- 若需要停止全部已确认 Fable classifier 上游调用，仍可切换现有 mock。
- 代码回滚后新增 setting 留在数据库不会影响旧二进制。

## Risks

- 通用 detector 过宽可能改写仿冒 Claude Code 的请求；通过 system allowlist、唯一 classifier block 和唯一 user 输入结构降低风险。UA 仍不是密码学身份证明。
- 官方 prompt 文案未来可能变化；多标记匹配比完整 hash 稳定，但核心标记全部变化时仍会漏算。日志应记录未包含正文的 detector 摘要，便于后续扩展。
- CCH 刷新若顺序错误会继续触发 429；测试必须以最终序列化 body 为输入验证。
- `x-app=cli` 会覆盖真实 Haiku旧画像，但 Haiku永不注入；该分支主要用于证明 detector 完整性，不改变其请求。
