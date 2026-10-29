# TLS ClientHello 采集设计

## 范围与依据

- 采用固定 mitmproxy 11.1.3 的 `tls_clienthello` 事件，公开 API 与字节封装已由 `research/clienthello-api.md` 和六条独立样本核实；各入口与预览边界见 `research/capture-integration.md`。
- 仅在已有 full capture 开启时追加 ClientHello。普通 capture、续聊、Projects、warmup 共用 Recorder，不改变 HTTP scope、CLI 租约或 cc2api TLS 模板。
- 不新增数据库列或通用文件下载接口。`capture_summary` 的安全 TLS 摘要供现有普通 run 与双迭代详情共用。

## 采集与字节合同

- 新增 sidecar 纯解析辅助模块，Recorder 在 hook 中取得 `data.client_hello.raw_bytes(wrap_in_record=False)` 和 `data.context.client.id`。文件从 `CAPTURE_FILE` 父目录派生为 `tls_clienthello.jsonl`。
- 每行 `schema=1`、事件标识／时间、`direction=client_to_recorder`、`client_connection_id`、执行上下文、解析状态、有序字段和原始本体。一个连接可以关联多个 HTTP flow，不在握手时伪造尚不存在的 flow ID。
- 原始内容标明 `raw_format=clienthello_body`、`tls_record_preserved=false`；`raw_base64/raw_bytes/raw_saved_bytes/raw_sha256/raw_truncated` 分别表示保存本体、全长、保存长度、完整本体 SHA256 和截断事实。不含 record 或 handshake 头，不声称是 pcap、原始 record 分片或代理上游握手。
- 有序字段为 `legacy_version`、`cipher_suites`、`extensions`（类型、原始扩展内容、长度）、`signature_algorithms`、`supported_groups`、`supported_versions`、`ec_point_formats`、`key_share`（组和实际长度）、SNI 和有序 ALPN 原始字节。合法缺失向量与解析错误分开；未知 ID 和 GREASE 原样保留。
- JA3 保存标准五字段字符串与 MD5，使用 legacy_version，按原顺序投影，计算时仅过滤标准 GREASE；其余字段独立保留，不把 JA3 当完整画像。
- 对长度、向量偶数性与 key_share 边界做严格检查；合法空 key_share 保持有效。异常保存可用原始证据、固定错误码，不伪造完整指纹。256 KiB 上限覆盖合法本体；超限保留此前缀、完整长度及摘要，明确 `parse_status=oversize/raw_truncated=true`。解析状态为 `ok/error/unsupported/oversize`，JA3 采用 `{string, md5}`；有序扩展为 `{type,length,data_base64}`，key_share 为 `{group,key_exchange_length}`，ALPN 为 `{text,base64}`。
- 显式非目标 SNI 在 target scope 下不采集；`scope=all` 采全部。无 SNI／目标暂不可判定时可保留并明确标记待归因，不据 IP 或目录断言官方 CLI。此策略不改 HTTP 过滤。
- TLS 文件独占安全创建并以 `0600` 追加，拒绝跟随文件链接；错误使用现有私有统计通道的固定消息，不抛出阻断 TLS／HTTP 转发的异常。DTLS／QUIC／ECH 内层及重试握手派发的完整覆盖不在本轮声称范围内。

## 执行上下文传播

- `CAPTURE_CONTEXT` 为新增私有 JSON，`schema=1`、`source`、`claude_code_version`，有真实快照时补 `claude_code_version_source`。普通及续聊填写真实 `run_id`；双迭代填写 `namespace/work_id`，不把 Pi 的兼容 `job.run_id` 当 runs.id。
- 在 Runner 普通／续聊、AccountRuntime 普通／续聊及 PiTerminal capture 分支使用本次真正装载的冻结版本；进入 network-context 的显式环境允许列表。
- Recorder 启动时解析成固定快照，核对已有 `QUOTA_SOURCE`，仅保留受支持字段。缺失／无效／归属冲突明确记录未知和固定上下文错误，不猜当前全局或账号默认值，不影响业务转发。
- 版本代表执行配置，不能独立证明每条连接都由官方 CLI 发起；线上样本须用连接键和真实 Claude 主请求进一步核对。
- 本轮复用现有 source/mode 网络 ACK，不新增跨版本 ACK 字段；用真实启动环境和产物字段验证元数据传播，不声称 ACK 本身已证明版本。
- HTTP 原始记录和轻量索引新增同名 `client_connection_id`，并可附受限执行上下文；保留已有 `analysis.cc_version` 的 HTTP 观察语义。
- v3 COPY 目录自然包含新模块，旧 sidecar Dockerfile 的显式 COPY 同步补齐。新文件沿既有组和执行目录追加，恢复同 source 也不覆盖旧字节。

## 读取与展示

- 文件列表沿现有递归逻辑包含 TLS 文件，旧目录缺失 TLS 正常返回不可用摘要。
- `capture_summary` 增加 `tls_clienthello` 安全摘要，全组共用 4 MiB、256 行、64 条有效记录预算，单行最多 512 KiB，公开向量最多 4096 项。显示可用、截断／错误状态及有限的安全记录；不完整时 `count_exact=false/total_records=null`，不能把截断扫描数冒充全量精确计数。
- 同一个白名单解析器供摘要和 Projects/warmup 既有 `/capture/file` 预览复用。保留路径、归属、链接、空间隔离检查；不新增普通 run 文件路由。
- 白名单只显示时间、方向、连接、执行版本／来源、公开数值向量、SNI／ALPN、key_share 组／长度、JA3 与状态。逐层重建嵌套字段，排除原始本体、扩展 payload、session/ticket/PSK/binder、未知自带字段和原始异常。
- 共用 `renderCaptureDetail` 在普通 run、Projects、warmup 详情显示该安全摘要，使用现有转义规则；原 HTTP／flow 权限保持，历史数据与既有异步归属保护继续有效。

## 验证、交付与回退

- 单元核算法／长度／GREASE／错误／私有权限／链接与嵌套 canary；入口核冻结版本、真实 run/work 和环境允许列表；预览核全组预算、半行、旧文件及双空间隔离。
- 真 mitmdump 11.1.3＋本地 TLS1.2／1.3 客户端＋模拟上游完成 HTTPS，多请求复用同一连接；独立解析已保存本体、核两个官方 JA3 向量及 HTTP 连接键。合成验证不冒充官方 CLI。
- 严格限定本任务文件提交；用户授权独立完成推送、匹配 Actions、us v3 部署与线上产物核查，不重复请求确认。保留其他变更，沿用不备份、不重算资源的 us 选择。
- 新增字段为兼容增量；回退代码仍保留已生成证据。部署遵守真实占用、输入对账及 Recorder 收尾，不能为验证随意强停健康 API。上线核对新镜像源码及正常项目采集的记录、冻结版本和 Claude HTTP 关联；不把历史 `.flow` 重新包装成新原始握手。
