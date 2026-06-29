# 技术设计

## 设计原则

- 只把 `/v1/messages` 顶层 key 顺序作为 wire 指纹处理，不引入全局 JSON formatter。
- `serde_json/preserve_order` 是基础能力；是否执行 profile reorder 由 setting 控制。
- CCH 输入必须是排序后的最终 body 字节。
- 设置默认开启，但必须可关闭以便线上对照和快速回滚。

## Setting

新增 setting：`message_body_order_fingerprint_enabled`

- 默认：`true`
- 解析：字符串布尔，沿用现有 settings flag 解析习惯。
- 生效范围：`GatewayService` 缓存到 `RwLock<bool>`，请求热路径只读缓存。
- 保存设置后 reload，前端 Settings 增加 toggle。

## 数据流

1. `GatewayService` 读取 setting，并将 bool 传入 `Rewriter::rewrite_body_with_stateful_completion` / `rewrite_body`。
2. `Rewriter` 解析和改写 body。
3. 若 path 为 `/v1/messages` 且开关开启，调用 `order_message_body_top_level_fields(&mut parsed)`。
4. 序列化为 bytes。
5. billing rewrite/API mimicry 按最终 bytes 计算 CCH。

## 排序策略

根据 body 结构选择 profile：

- Haiku 非流探测：`model` 包含 `haiku`，`max_tokens=1`，无 `system` / `tools`。
- Haiku 流式标题：`model` 包含 `haiku`，`stream=true`，`tools` 为空，存在 `temperature`。
- 默认 messages 主请求：使用 Opus 主请求顺序。

排序函数只处理 top-level object：

- 先按 profile 顺序移出已知字段并重插。
- 再把原对象剩余字段按原相对顺序追加。
- 非 object body 原样返回。

## 兼容性

- `serde_json/preserve_order` 会影响 `Value::Object` 的底层 map 类型；测试中不能依赖对象按字母排序。
- 其它 endpoint 不调用排序函数，行为应保持不变。
- 如果管理员关闭开关，仍保留 preserve_order feature，但不会主动重排 `/v1/messages` 顶层字段。

## 风险与回滚

- 风险：排序函数误判 body 形态，导致字段顺序不符合抓包。通过三类抓包 shape 单测覆盖。
- 风险：新增参数影响调用点。统一更新 `GatewayService` 和测试 helper。
- 回滚：把 setting 改为 `false`，或后续移除排序调用。
