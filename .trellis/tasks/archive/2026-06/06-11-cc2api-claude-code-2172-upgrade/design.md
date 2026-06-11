# cc2api 升级 Claude Code 2.1.172 技术设计

## Technical Design

本任务修改 `/root/project/cc2api`，Trellis 任务记录保存在 `vibecoding-bench` 仓库。

版本画像继续集中在 cc2api 现有 version profile / access policy / migration 结构中更新。默认版本、基础版本、build time、默认允许范围和 OAuth usage User-Agent 必须一致，避免 runner、请求体和 usage API UA 出现版本错位。

请求头画像需要按端点区分：

- `/v1/messages?beta=true` 使用 `User-Agent: claude-cli/2.1.172 (external, cli)`。
- bootstrap 使用 `User-Agent: claude-code/2.1.172`。
- `X-Stainless-Package-Version=0.94.0`、`X-Stainless-Runtime=node`、`X-Stainless-Runtime-Version=v24.3.0`、`X-Stainless-Timeout=600`、`anthropic-version=2023-06-01`、`x-app=cli` 保持抓包值。
- 不因 Fable 额外添加新的 header 名；Fable 差异由 `anthropic-beta` 和请求体表达。

Beta 列表必须由模型/profile 生成，不能只按 Claude Code 版本统一拼接：

- Haiku/title 请求保持轻量 beta profile，不带 `claude-code-20250219` 和 `context-1m-2025-08-07`。
- Opus `claude-opus-4-8[1m]` 主请求保留 `context-1m-2025-08-07`。
- Fable `claude-fable-5` 主请求不带 `context-1m-2025-08-07`，新增 `server-side-fallback-2026-06-01` 与 `fallback-credit-2026-06-01`。

CCH 实现需要从“按版本选 seed”升级为“按版本选输入 profile”：

- `2.1.156` / `2.1.169`：seed `0x4D659218E32A3268`，输入为完整最终 JSON body，仅把真实 `cch` 替回 `00000`。
- `2.1.172`：seed 仍为 `0x4D659218E32A3268`，输入为最终 JSON body 的规范化视图：
  - top-level `model` 只保留字段结构，排除字符串值。
  - top-level `max_tokens` 整个字段排除，包含前导逗号。
  - top-level `fallbacks` 存在时整个字段排除，包含前导逗号。

实现时优先基于已经序列化的最终 body 字节做有边界的 JSON 字段裁剪，不能重新 `serde_json` 序列化后再 hash，否则字段顺序、转义和空格可能改变 CCH。字段裁剪必须只作用 top-level 字段，不能误删 tool schema、message content 或嵌套对象中的同名字段。

Fable 请求画像需要和抓包一致：请求 model 为 `claude-fable-5`，主请求存在 `fallbacks:[{"model":"claude-opus-4-8"}]`；该字段参与实际请求发送，但不参与 172 CCH hash 输入。

Bootstrap profile 需要表达 172 服务端能力开关：

- 169 保持 `client_data=null`、`additional_model_options=null`、`cwk_cfg_key=null`。
- 172 Opus response 表达 `client_data.cedar_lagoon` 开启 `claude-fable` / `claude-mythos`，并在 `additional_model_options` 暴露 `claude-fable-5[1m]`。
- 172 Fable response 在上述基础上返回 `cwk_cfg_key="marigold"`。

Telemetry 如果 cc2api 现有代码会生成或改写，需要按 profile 更新：

- 172 统一 `env.version=2.1.172`、`env.version_base=2.1.172`、`env.build_time=2026-06-10T16:30:37Z`。
- Opus `[1m]` telemetry 可继续使用 `model=claude-opus-4-8[1m]`，API success 可按现有画像保留 `preNormalizedModel=claude-opus-4-8[1m]`。
- Fable 主请求相关 telemetry 使用 `model=claude-fable-5`，`betas` 与 Fable 主请求 profile 一致。
- `flags=model` 是 CLI `--model` 一次性覆盖信号；实现上应由调用上下文显式传入，不能因为模型是 Fable 就无条件生成。

测试策略：

- 对 169/172 各保留脱敏最小 fixture，body 保留字段结构和 CCH 相关片段，删除敏感 prompt / token。
- 单元测试直接验证 CCH profile 函数：169 完整 body 命中；172 Opus 去 `model/max_tokens` 命中；172 Fable 额外去 `fallbacks` 命中。
- 测试 top-level 限定：嵌套 `fallbacks`、`model`、`max_tokens` 不应被裁剪。
- 增加 header/beta/profile 快照或等价断言，覆盖 Opus 1m、Fable fallback、Haiku/title 三类请求。
- 增加 bootstrap 和 telemetry profile 测试；若项目当前没有 telemetry 生成路径，则至少确认 172 常量和 profile 不会误导现有逻辑。

## Rollout / Rollback

升级属于默认画像与请求签名行为变更。回滚时恢复默认版本到 `2.1.169`，并保持旧版本 profile 不变。若 172 CCH 在线出现不匹配，应优先通过设置或版本 profile 回退到 `2.1.169`，不要全局改 seed。
