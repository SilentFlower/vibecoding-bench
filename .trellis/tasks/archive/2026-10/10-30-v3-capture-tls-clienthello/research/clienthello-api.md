# Research: ClientHello 采集 API、原始封装与 JA3

- Query: 核实固定 mitmproxy 11.1.3 的握手钩子、原始字节、连接身份、JA3 规则及独立验证方法。
- Scope: mixed
- Date: 2026-10-30

## Findings

### 已核对的来源与文件

- 当前生产账号网络容器内 `/opt/mitm/bin/python` 只读输出 `mitmproxy.version.VERSION == "11.1.3"`，并核对以下已安装类定义；没有修改环境、启动模型或读取凭据。
- `mitmproxy/tls.py`：`ClientHello`、`ClientHelloData` 的固定版本公开 API。
- `mitmproxy/proxy/context.py`：`Context.client`、`Context.fork()` 的同一客户端连接引用。
- `mitmproxy/flow.py::Flow.__init__`：直接保存调用方传入的 `client_conn`，另行生成 `flow.id`。
- `images/sidecar/recorder.py:404`：现有 Recorder 状态；`:450` 附近为 HTTP 分阶段持久化入口，当前没有 ClientHello hook。
- `images/sidecar/recorder.py:310`：HTTP 轻量索引入口，新增连接关联须同时进入完整 HTTP 记录和索引。
- `images/account/network-context.py:193`：网络 context 显式允许列表，新增执行元数据必须穿过该边界。
- `.trellis/tasks/10-29-cc2api-vm2api-wire-differential-study/research/tls-evidence.json`：既有六条本地模拟上游的初始握手，可用于独立字段解析对照，不能称作原生官方 CLI 抓包。

### 固定版本公开 API

| 位置 | 实际定义／语义 |
| --- | --- |
| addon hook | `tls_clienthello(self, data: mitmproxy.tls.ClientHelloData)` |
| `data.client_hello` | `mitmproxy.tls.ClientHello` |
| `data.context.client.id` | 客户端 `connection.Client` 的字符串 ID |
| `data.context.server.id` | 独立服务端连接的 ID；不能当作客户端握手 ID |
| `hello.raw_bytes(wrap_in_record=False)` | 精确 ClientHello **本体**，从 `legacy_version` 开始 |
| `hello.cipher_suites` | `list[int]`，客户端有序 offer |
| `hello.extensions` | `list[tuple[int, bytes]]`，有序扩展类型与原始扩展正文 |
| `hello.sni` | `str | None`；SDK 对单一合法主机名进行解析 |
| `hello.alpn_protocols` | `list[bytes]`；必须保留原始字节和顺序，不能默认任何 ALPN 都是 UTF-8 |

固定版本 `ClientHello` 没有公开的 `version`、`supported_groups`、`signature_algorithms` 或 `key_share` 属性。不要访问猜测的字段。`legacy_version` 可从本体头两个网络字节读取；后三类向量从原始扩展严格解析。

### 原始字节的边界

`raw_bytes(False)` 不含 5 字节 TLS record 头，也不含 4 字节 TLS handshake 头。固定版本 TLS layer 先拼接可能跨 record 的握手，再去掉 handshake 头构造 `ClientHello`。

默认 `raw_bytes()` 则人为拼接：`16 03 03`、合成 record 长度、`01`、合成 uint24 长度、原始本体。默认 record version 固定为 0x0303，不保证等于线上 record 版本。因此建议记录 `raw_format="clienthello_body"`、提取接口与长度／摘要，明确 `tls_record_preserved=false`；可另由本体生成分析工具兼容封装，但不得称其为原始 pcap 或原始 record 分片。

DTLS 分支的 `raw_bytes` 在该版本明确抛 `NotImplementedError`。本任务 TCP TLS 采集应标明 transport；不要把不支持的 DTLS／QUIC 声称为已覆盖。

### 有序字段的最小解析合同

| 扩展 | 客户端扩展正文 | 采集结果 |
| --- | --- | --- |
| 10 supported_groups | uint16 字节长度，随后 uint16 组列表 | 原序整数，保留未知组和 GREASE |
| 11 ec_point_formats | uint8 字节长度，随后 uint8 格式列表 | 原序整数，用于 JA3 第五字段 |
| 13 signature_algorithms | uint16 字节长度，随后 uint16 scheme 列表 | 原序整数，不用名字表丢弃未知值 |
| 43 supported_versions | ClientHello 中为 uint8 字节长度，随后 uint16 版本列表 | 原序整数，与 legacy_version 分开保存 |
| 51 key_share | uint16 总长度，随后重复 group:uint16、exchange_len:uint16、exchange bytes | 原序 group 和实际 key 长度；完整字节仍在私有 raw 中 |

按长度字段逐段检查边界；uint16 列表必须为偶数字节。key_share 的整体客户端列表允许为空，这是合法的 HelloRetryRequest 前置行为；不能把空列表当成截断。解析结构长度，不依据已知组表硬编码公钥长度，以兼容未知组／PQ 组合。

扩展应保留列表，不转换成按类型键控的字典，以免丢顺序或覆盖重复条目。未知扩展的整数类型、原始正文、长度均保留；已知向量异常记录解析错误并保留原始本体，不生成“完整解析成功”的假指纹。缺少扩展与解析失败是不同状态。

### JA3 的准确计算与局限

JA3 是五个十进制字段依原序拼接：`legacy_version,ciphers,extensions,supported_groups,ec_point_formats`。各向量以连字符连接，各字段以逗号连接，空字段仍保留逗号。对该字符串做 MD5 得到 32 位十六进制摘要。

仅在 JA3 投影中排除 cipher、extension type、supported_groups 中的 16 个 GREASE 值：`0x0a0a + 0x1010*n (0<=n<16)`。原始证据与有序解析结果不能删除 GREASE。JA3 不排序向量；RFC 8701 也将类似值用于 signature schemes／versions，但它们的实际值本来就不进入 JA3。

TLS 1.3 ClientHello 的 legacy_version 按 RFC 为 0x0303（771）；支持 1.3 在 supported_versions 中报告。不能用协商后的 `TLSv1.3` 写成 772 来算 JA3，更不能使用合成 record 头版本。

JA3 不包含 signature_algorithms、ALPN、key_share 的**具体值**，只包含相关扩展 ID；修改这些向量仍可能得到相同 JA3。必须保留其独立字段和完整有序扩展。JA3 只是辅助比较，不能作为完整 TLS 画像或安全身份。

Salesforce 官方 README 的固定验证向量：

| JA3 字符串 | MD5 |
| --- | --- |
| `769,47-53-5-10-49161-49162-49171-49172-50-56-19-4,0-10-11,23-24-25,0` | `ada70206e40642a3e4461f35503241d5` |
| `769,4-5-10-9-100-98-3-6-19-18-99,,,` | `de350869b8c85de67a350c8d186f11e6` |

### 连接关联与来源归因

`Context.fork()` 保留同一 `client` 对象。`Flow.__init__` 保存传入客户端连接，`flow.id` 是另一个 HTTP flow 标识。TLS 钩子存 `data.context.client.id`，HTTP 钩子存 `flow.client_conn.id`，用同一键建立一条 TLS 连接到多个 HTTP flow 的关系，支持 keep-alive／HTTP/2，握手发生时无需猜测尚不存在的 HTTP flow ID。

方向固定标为客户端→Recorder。不能把 `context.server` 或后续 `server_conn` 的协商元数据当作原生客户端 offer；上游可能是 mitmproxy／OpenSSL 的握手。

执行冻结 CLI 版本只能证明采集所属执行上下文，不足以独立证明每条连接都由官方 CLI 发出：项目子进程也可能发 TLS。线上正式样本须用连接 ID 进一步关联真实 Claude HTTP 主请求，并结合实际运行版本及采集条件判定；仅凭文件目录、SNI 或环境版本不可冒充客户端进程证明。

### 隐私与故障边界

完整本体／原始扩展可能包含 TLS 1.2 session ticket、TLS 1.3 PSK identity／binder 和客户端 session ID；它们不应进入公开摘要或 API 原文预览。保留在既有私有证据目录，安全预览只选择版本、指纹、类型／算法／组列表、key_share 组与长度、连接关联等已定义字段；未知扩展 raw 不应因为“未知”就被直接公开。

采集回调是观察者，不改 `ignore_connection`、`establish_server_tls_first` 或 TLS 配置。不为取得指纹新增上游握手／模型请求；解析或写入错误不能阻断转发，也不能把丢证据误报成完整。

### 验证建议

已完成两项独立验证：`clienthello-api-known-vectors.json` 中两条 Salesforce 官方 JA3 字符串的 MD5 全部匹配；`clienthello-api-probe.py` 通过生产现有容器的固定 SDK 对既有六条模拟握手执行独立游标解析，六条全部通过，结果见 `clienthello-api-probe.json`。探针断言了原始本体、默认合成封装、有序 cipher／扩展、ALPN，以及旧证据内的版本／算法／组／key_share 字段，并独立计算 JA3。运行仅执行只读解释器与内存解析，没有启动 TLS 请求或写入生产文件。

该探针只证明固定 SDK 与既有模拟样本的字段合同，并未证明新采集 hook 已工作，也未证明真实 HTTP 流与握手已关联。

1. 在固定 11.1.3 SDK 中，对原始本体、默认合成封装和以上公开属性做精确字节断言；用另一段独立游标解析器核对有序扩展、算法、组、key_share 与两个官方 JA3 向量。
2. 使用原研究六条合成握手核对 SDK 解析；这些是独立已有样本，不能标作本任务新采集的官方 CLI。
3. 正式实现后用真实 mitmdump＋本地 TLS1.2／1.3 客户端和模拟上游完成握手及 HTTP 请求，记录两条以上复用同连接的请求，断言 TLS/HTTP 连接键一致；这个 E2E 不能用纯 `ClientHello` 构造器替代。
4. 覆盖 GREASE、未知扩展、无 SNI／无 ALPN、合法空 key_share、超长／奇数／截断向量、写入异常，确保原始证据保留且业务不中断。

## External references

- [mitmproxy v11.1.3 ClientHello 与 ClientHelloData](https://github.com/mitmproxy/mitmproxy/blob/v11.1.3/mitmproxy/tls.py)：同时经生产已安装源码只读核对。
- [mitmproxy v11.1.3 TLS layer](https://github.com/mitmproxy/mitmproxy/blob/v11.1.3/mitmproxy/proxy/layers/tls.py)：握手 record 拼接及去除 handshake 头。
- [Salesforce JA3 README](https://github.com/salesforce/ja3/blob/master/README.md#how-it-works)、[官方 Python 实现](https://github.com/salesforce/ja3/blob/master/python/ja3.py)：字段顺序、GREASE 和固定向量。
- [RFC 8446 §4.1.2](https://www.rfc-editor.org/rfc/rfc8446.html#section-4.1.2)、[§4.2.3](https://www.rfc-editor.org/rfc/rfc8446.html#section-4.2.3)、[§4.2.7](https://www.rfc-editor.org/rfc/rfc8446.html#section-4.2.7)、[§4.2.8](https://www.rfc-editor.org/rfc/rfc8446.html#section-4.2.8)：ClientHello 及有序向量。
- [RFC 8701 §2](https://www.rfc-editor.org/rfc/rfc8701.html#section-2)：完整 GREASE 取值。

## Related specs

- `.trellis/spec/vibecoding-bench/deploy/official-protocol-capture.md:167`：条件标识及 TLS 原生／代理方向边界。
- `.trellis/spec/vibecoding-bench/backend/account-runtime-v3.md:889`：冻结 CLI 版本、分代采集、双迭代空间、受限预览。
- `.trellis/spec/vibecoding-bench/backend/project-iterations.md:983`：同工作恢复的启动尝试独占，原会话／来源归因保持。

## Caveats / Not Found

- 当前已核实固定 API、两条官方算法向量与六条既有模拟样本；真实握手回调与 HTTP 关联的完整 E2E 必须在实现后验证，不能声称已经完成采集。
- 未研究 JA4、官方 280／293／303 的无解密透传对照、HelloRetryRequest 二次 ClientHello 在固定代理层的实际派发次数、DTLS／QUIC/ECH 内部握手；不会将这些记为已覆盖。
- 本研究不改产品、spec、部署状态或其他任务。探针语法注释及输出只作研究验证，不代替产品解析器或其边界测试。
