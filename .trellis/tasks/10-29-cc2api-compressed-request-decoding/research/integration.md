# 压缩请求的现有调用边界

核对日期：2026-10-29。子仓基线 `669f3d78fa9d45247c8989c4d5240c4898ee6e0c`；本研究阶段产品代码未改动。

## 入口与原始头

- `cc2api/src/handler/router.rs` 的 `gateway_fallback`／`gateway_count_tokens` 先进行 API token 鉴权，再调用 Gateway。保持此顺序。
- `gateway.rs:1751` 通用入口先从原始头获得 UA 并在同一个读锁中完成访问策略和画像快照，随后在 `:1786` 读取最多 10 MiB 的原字节。需要在请求仍可访问 HeaderMap 时保存全部 Content-Encoding；编码校验／解码在 UA 准入后、任何正文策略与账号选择前执行。
- `gateway.rs:1545` count_tokens 另有入口：POST 校验、UA 准入、10 MiB 读取、空体／JSON object／model 校验。压缩输入解码后仍执行这些原校验，不套用 Messages 的根键过滤或 Session 规则。
- `extract_headers` 在 `:3212` 只对 beta 特殊合并，其它头会覆盖或跳过非法字符串；不能把这个 HashMap 当作编码链的无损来源。不要顺带更改其它头收集规则。
- 通用入口的 JSON 解析和 `Rewriter::rewrite_body_inner` 对非 JSON 存在既有回退。编解码模块仅处理字节，不能新增全局 JSON object 校验或改变 artifact／其它端点的正文语义。

## 保持逻辑正文贯穿业务链路

- 原始逻辑正文参与客户端识别、prefill／warmup／classifier、本地缓存、sticky、slot／RPM、Session 池及 Hello。压缩输入应先解码再走这些已有步骤，不提前换成上游 Session。
- `gateway.rs:2200` 附近的改写与过滤 CCH 刷新先完成，随后解析最终逻辑 body；mapped Session 头处理在普通有限对齐之前。
- `:2252` 自动遥测 context、`:2330` 非流探针缓存、usage 和诊断都使用逻辑正文。不要把这里的 `final_body` 提前替换为压缩字节，也不把编码容器参数加入业务缓存键。
- `:2380` 主发送、`:2434` OAuth 401 重试都进入 `forward_request`；外层 429／凭据切号会重新按账号改写逻辑正文。
- `maybe_retry_signature_error` 在 `:2641` 从逻辑 JSON 移除指定历史块，再调用现有 `refresh_cch_attestation` 并进入 `forward_request`。每一阶段必须对本次正文重编码，不能复用初次请求的压缩字节。
- count_tokens 的初次和 401 重试都调用 `forward_count_tokens_request`（`:3067`）。编码计划应在单个请求内冻结，贯穿这两条发送路径和 signature 重试。

## 最后的网络边界

- `forward_request`（`:2737`）先用逻辑正文调用 `diagnostics::begin_attempt`，构造 `PreparedRequest`，再调用 `runtime_transport::send`。`forward_count_tokens_request` 也构造同一元信息类型。
- `runtime_transport.rs:51` 的 `PreparedRequest` 将元信息与 body 分开，没有编码字段。本项只把匹配的 Content-Encoding 放进已有 headers，把最终编码 bytes 交给已有 send，不新增桥协议字段。
- `runtime_transport.rs:147` 的 `send_with_client` 使用 `.body(Vec<u8>)`，HTTP/1 大小写列表仅额外声明 Content-Length 的拼写，长度交给实际 body 自动生成。发送前删除旧 Content-Length／Transfer-Encoding 和大小写变体，按最终编码链写入唯一 Content-Encoding。
- `rewriter.rs:1001` 的 `ordered_anthropic_headers` 保留已有画像列表，再按名字排序附加其它头。Content-Encoding 沿用此机制，不凭公开 gzip 说明杜撰 300 的精确头顺序。
- `runtime_transport.rs:181` 的 send 覆盖直连及 v3；桥的 `:253` 使用最终原始 bytes 作为内部请求正文；账号发送器 `:402` 只转交 bytes；`:479` 既有内部接收上限为 128 MiB。本项不改这些协议或接收上限。

## 复用与边界

- `gateway.rs:3757–3834` 是宽松的响应解码工具，不能用于严格有界入站；其行为也不在本项改动范围。
- `anthropic_error_response` 可用于本地编解码拒绝，保持可解析 Anthropic error object；无需为了 413／415 扩大全局 AppError 枚举。
- 编码工作放在最终网络提交前，诊断和错误分类保留逻辑正文；压缩失败不提交业务请求，不新增明文回退重试。
- 上述行号针对当前基线。实现前必须重新读取实际函数定义和所有调用点，不能凭本文件猜签名。
