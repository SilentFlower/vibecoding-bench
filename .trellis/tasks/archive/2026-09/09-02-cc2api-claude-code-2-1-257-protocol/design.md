# 技术设计

## 设计目标

把 2.1.257 协议差异收口到版本画像和可测试的请求分类中，避免继续在 rewriter 热路径里
按版本字符串散落分支。旧画像保持只读兼容，默认画像切换到 2.1.257。

## 画像结构

在 `src/service/version_profile.rs` 扩展现有 `ClaudeCodeProfile`：

- identity 保持版本、build time、Stainless 和 Node runtime 归属画像。
- request 增加模型/请求类型子画像，至少区分通用 Opus、Fable 5、Fable 5.1、Haiku
  probe、Haiku title、Haiku main、Haiku non-stream aux。
- Fable fallback 使用明确枚举表达“模型数组”和字符串 `"default"`，不通过一个
  `fable_fallback_model` 字段猜测 JSON shape。
- CCH profile 表达 top-level `model`、`max_tokens`、`fallbacks` 的归一化策略；
  2.1.257 根据最终模型决定是否保留 fallback。
- endpoint profile 保存 Bun UA、bootstrap cedar/cwk 等版本差异；旧 profile 值不变。

所有公开结构和方法按项目规范补齐中文 Javadoc，避免新增无说明的公共契约。

## 请求分类与改写

在 `src/service/rewriter.rs` 中：

- 使用精确模型集合识别 `claude-fable-5` 与 `claude-fable-5-1`；family helper 只用于
  明确共享的配额/展示语义，不用宽泛 prefix 决定 wire profile。
- 原生 Claude Code 请求保留客户端已有字段，只补画像要求且缺失的字段；API mimicry
  按画像补齐 max tokens、fallback、thinking 和字段顺序。
- Fable 5.1 的 beta、fallback、thinking display 和 CCH 与 Fable 5 分开。
- CCH 计算先按画像生成最终 body，再做字节级 top-level 归一化；不通过 JSON
  反序列化重排 hash 输入。
- 提取可复用的结构化 Haiku title 判定，识别 JSON schema 中唯一必需的 `title` 字段；
  rewriter 与 gateway 拦截器共用同一判定，保留旧字符串 marker。
- Haiku main 根据 diagnostics 等真实结构选择子画像；1024 非流式辅助请求只按已确认
  结构选择窄 beta，不为其猜测业务名称。

## 设置与数据库迁移

在 `src/store/settings_store.rs`、`src/store/db.rs`、`src/handler/router.rs` 和设置页中：

- 默认 profile/range 更新到 2.1.257；历史默认组合条件迁移，自定义 range 保留。
- `allow_system_role_models` 默认加入 `claude-fable-5-1`。增加一次性追加式迁移：读取
  现有逗号列表、精确去重后追加新 ID，保留 `claude-sonnet-5` 等自定义值。
- bootstrap configured 默认 option 更新为 5.1 `[1m]`，只迁移仍等于旧默认的值；
  profile 中的 `sorrel` / cedar 控制版本差异。
- 不迁移 `allow_1m_models`、`rewrite_disabled_thinking_models` 和
  `intercept_assistant_prefill_models`。
- 账号 canonical env 迁移复用现有启动迁移，仅更新画像身份字段，不改变账号能力开关。

## Fable Family 配额

在 `src/service/account.rs` 中将已知的两个 Fable 模型映射到同一个
`seven_day_fable` family：

- 新会话候选账号过滤；
- sticky account 到阈值后的 fallback；
- Fable 模型级 429 的账号排除与换号。

模型识别使用精确 ID 和已知 `[suffix]` 形式，避免未来其他 `claude-fable-*` 模型被
未经验证地纳入同一行为。

## 首字节超时诊断

在 `src/service/gateway.rs` 调用 `stable_upstream_stream` 前，从上游响应头提取脱敏
`request-id` / `x-request-id` 并传入 stream state：

- `chunk_count == 0` 超时记录 `upstream_first_byte_timeout`、request ID、等待毫秒和
  account；
- 已收到 chunk 后超时继续记录 `upstream_stream_idle_timeout`、chunk 数和最大间隔；
- keepalive 只在 `first_chunk_seen=true` 后生效；
- 日志不记录 body、prompt、Authorization、Cookie 或账号邮箱。

该设计只改善诊断，不改变对客户端的流字节，也不把 120 秒无限放大到 Claude Code 的
184 秒 watchdog。

## 测试设计

- `version_profile.rs`：默认/回滚 identity、allowed range、beta 和 bootstrap profile。
- `rewriter.rs`：使用脱敏最小 JSON fixture 覆盖四类模型、body order、fallback、
  `cc_version`、CCH、Haiku 结构分类和 1M 过滤边界。
- `account.rs`：Fable 5/5.1 family 配额正例和相似模型反例。
- `gateway.rs`：system-role 白名单、title 拦截结构判定、0 chunk 首字节超时、首 chunk
  后 idle timeout、keepalive 边界和 request ID 日志上下文。
- `db.rs`：默认组合升级、自定义 range 保留、system-role 自定义列表追加、三个明确
  不迁移字段保持原值。
- Web：画像选项、默认值和表单保存构建验证。

## 兼容性与回滚

- 2.1.220 profile 完整保留；管理员可以切回旧 profile 和 allowed range。
- 追加到 system-role 列表的 5.1 不会在代码回滚时自动移除，但只放宽该模型的
  system role，本身不改变其他模型。
- 数据库迁移前后不修改账号 `allow_1m_models`，所以回滚不会引入 1M 策略漂移。
- 若新画像异常，生产层回滚旧镜像和 DB 备份；抓包原始数据不参与运行时依赖。
