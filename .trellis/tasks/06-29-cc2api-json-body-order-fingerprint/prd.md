# cc2api 请求体 JSON 顺序指纹对齐

## Goal

为 `cc2api` 增加可配置的 `/v1/messages` JSON 顶层字段顺序对齐，降低 `serde_json` 重序列化导致的 body order 指纹偏差，并确保 CCH 在最终排序后的 body 上计算。

## 背景

- 2.1.195 抓包显示 `/v1/messages` body 顶层字段顺序稳定。
- 当前 `cc2api` 会把请求体解析为 `serde_json::Value` 后重新序列化；默认 `serde_json` 不保留 object 插入顺序。
- CCH 已在最终 body 上计算，因此排序修复不能发生在 CCH 之后。
- 用户要求 `preserve_order` 由全局 setting 开关控制，避免不可回滚地改变所有 JSON 行为。

## 需求

- 为 `serde_json` 开启 `preserve_order` crate feature，让 JSON object 能保留插入顺序。
- 新增全局 setting 控制 `/v1/messages` 顶层字段顺序对齐，默认开启以降低当前 2.1.195 指纹风险。
- 只对 `/v1/messages` 请求体执行顶层字段重排；其他 endpoint 不改变 body 顺序。
- 排序必须在 body 所有改写之后、CCH 计算之前执行。
- 根据 2.1.195 抓包对齐已知 body 形态：
  - Opus 主请求：`model,messages,system,tools,metadata,max_tokens,thinking,context_management,output_config,diagnostics,stream`
  - Haiku 流式标题：`model,messages,system,tools,metadata,max_tokens,thinking,temperature,output_config,stream`
  - Haiku `max_tokens=1` 探测：`model,max_tokens,messages,metadata`
- 未知额外字段不得丢弃；排在已知字段之后并保留其相对顺序。
- 支持设置页展示和保存该开关。
- 补充测试覆盖开启/关闭开关、三种已知 body 顺序、未知字段保留、CCH 在排序后计算。

## 非目标

- 不重写嵌套对象字段顺序。
- 不调整 telemetry `additional_metadata`，该项由大型任务 `cc2api-auto-telemetry-real-profile-alignment` 跟踪。
- 不在本任务中修 TLS/ALPN、代理连接池或工作目录透传策略。

## 验收标准

- [ ] `Cargo.toml` 中 `serde_json` 启用 `preserve_order`。
- [ ] settings 中存在可配置开关，默认开启，旧库迁移后有默认值。
- [ ] 开启开关时 `/v1/messages` 三种抓包 body 形态输出顶层 key 顺序与 2.1.195 抓包一致。
- [ ] 关闭开关时不执行额外顶层 key 重排。
- [ ] 额外未知字段保留在已知字段之后，字段值不丢失。
- [ ] billing/CCH 在排序后的最终 body 上计算。
- [ ] 前端 Settings 能展示和保存开关。
- [ ] `cargo fmt --check`、相关 Rust 测试、如改前端则 `npm run build` 通过。
