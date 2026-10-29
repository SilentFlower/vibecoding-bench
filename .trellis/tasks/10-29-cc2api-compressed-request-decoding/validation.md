# 压缩请求实施验证

## 基线与失败回归

- 产品基线：`669f3d78fa9d45247c8989c4d5240c4898ee6e0c`，开工时 `cc2api` 工作区干净；指纹见 `research/execution-baseline.json`。
- 仅先添加实际 Gateway 回归 `gateway_compressed_request_gzip_rewrites_before_sending`，产品编解码逻辑仍为基线。
- 命令：在 `cc2api/` 执行 `cargo test --locked gateway_compressed_request_gzip_rewrites_before_sending > /tmp/cc2api-compressed-request-red.log 2>&1`。
- 退出码：`101`；1 项失败。合成 loopback 实际收到的 `Content-Encoding` 为 `None`，预期为 `gzip`，复现 R3-03。
- 日志：`/tmp/cc2api-compressed-request-red.log`。测试使用合成账号与本地上游，不属于真实 Anthropic 推理或新版原生抓包。

## 实施后验证

工作目录均为 `/root/project/vibecoding-bench/cc2api`；重定向保留原始 stdout/stderr。最后一次完整验证后未再修改产品文件。

| 精确命令 | 退出码 | 实际结果／证据 |
| --- | --- | --- |
| `cargo test --locked request_body_codec` | 0 | codec agent 定向验证，16 项通过。实际结果摘要见 `/tmp/cc2api-request-body-codec-validation-20261029.md`；该文件不是完整原始 stdout/stderr，本轮没有为生成日志重复运行。16 项同样纳入下方最终全量原始日志。 |
| `cargo test --locked gateway_compressed_request > /tmp/cc2api-compressed-request-gateway-initial.log 2>&1` | 0 | 首轮 9 项 Gateway 集成回归通过，包含基线红灯转绿。之后新增缓存／本地拦截、读体错误和 Router 鉴权 3 项，统一纳入最终全量。 |
| `cargo fmt` | 0 | 最终格式收敛，仅约定三个产品文件存在差异。 |
| `cargo fmt --check > /tmp/cc2api-compressed-request-fmt-final.log 2>&1` | 0 | 无格式错误。 |
| `git diff --check > /tmp/cc2api-compressed-request-diff-check.log 2>&1` | 0 | 跟踪文件无空白错误。新 codec 另由下方独立新文件检查覆盖。 |
| `cargo test --locked > /tmp/cc2api-compressed-request-full-final.log 2>&1` | 0 | **745 passed、0 failed、3 ignored**；lib 为 677 passed／1 ignored，集成为 68 passed／2 ignored，doc tests 为 0。新增 16 项 codec＋12 项 Gateway 全部通过。 |
| `cargo test --locked cch > /tmp/cc2api-compressed-request-cch-final.log 2>&1` | 0 | 40 项 CCH 回归通过；其余 target 按筛选条件运行 0 项。 |

三个既有 ignored 分别为 `postgres_diagnostics_storage_contract`、`usage_limits_postgres_storage_and_legacy_migration`、`postgres_profile_settings_and_rollback`，均要求提供指向独立临时 PostgreSQL 的专用 DSN。本项未新增忽略项，也未修改数据库。

codec agent 在冻结文件上执行 `rustfmt --edition 2024 --check src/service/request_body_codec.rs` 退出 0；`git diff --no-index --check /dev/null src/service/request_body_codec.rs` 无空白错误输出、退出 1，原因是 `--no-index` 隐含差异退出码，不能记成退出 0。其交接 SHA 与最终 SHA 相同。Cargo 输出仍包含已有 vendor reqwest 的 cfg／dead-code 告警及 redis／sqlx-postgres future-incompatibility 提示，未改相关依赖。

## 实际覆盖

### codec：16 项模块单测

- 从原始多值头读取大小写、SP／HTAB、identity、空列表和 x-gzip 别名；完整 token 语法与未知编码分类；32 片段／33 片段和 4 层／5 层边界。
- gzip／x-gzip、标准 zlib-deflate、raw-deflate 兼容、标准 br、zstd，以及四层有序链；独立 reader 验证编码顺序，raw 入站重新编码为标准 zlib。
- 每个小样本的全部截断前缀、尾随垃圾／零填充、gzip 第二 member 的 CRC／ISIZE、zlib Adler32、zstd 第二 frame 的可选 checksum；合法多 gzip member、多 zstd frame／skippable frame 完整拼接，不丢后续明文。
- 原始字节及每层解码精确 10 MiB／加 1／中间层超限；恰好上限仍校验结尾；zstd 第一及后续 frame 的 16 MiB 窗口边界、标准 br 与 large-window 扩展边界。
- 无编码 decode 保留 Bytes 存储、encode 返回 Cow::Borrowed，不嗅探 magic；有效编码使用 blocking worker；重编码允许真实容器膨胀超过入站读取上限。

### 实际 Gateway：12 项集成回归

| 测试 | 直接断言 |
| --- | --- |
| `gateway_compressed_request_gzip_rewrites_before_sending` | 基线缺陷转绿；实际 CE／CL／wire bytes、根键清理、Session 与最终画像 CCH。 |
| `gateway_compressed_request_messages_match_plaintext` | 120 次实际发送：CC／API × 3 种 stream × 过滤开／关 × 明文及 9 个编码样例；解码后的最终逻辑字节逐项等于明文基线，身份、Session、CCH、beta query 与实际 JSON／SSE 响应一致。 |
| `gateway_compressed_request_other_endpoints_match_plaintext` | 80 次实际发送：CC／API × count_tokens／event_logging／通用非 JSON 路径 × 明文及 9 个编码样例；计数专用清理、遥测身份改写、非 JSON 原字节及规范编码／长度一致。 |
| `gateway_compressed_request_rejections_have_no_account_side_effects` | 13 类输入 × 4 个入口；未知 415、畸形／截断／校验／尾随 400、原始／最终／中间层超限 413，均为 Anthropic error object。实际业务上游、账号缓存读取、绑定写入、RPM／slot admission、池解析、Hello 状态／网络、OAuth 刷新及自动遥测会话均为零。 |
| `gateway_compressed_request_preserves_admission_and_plaintext_semantics` | 无编码／只有 Accept-Encoding／identity／空列表保持原语义；普通 Gateway 非 JSON 透传，count_tokens 严格拒绝；无声明不嗅探 gzip；UA 拒绝先于编码错误，count_tokens 非 POST 先于 UA／编码错误。 |
| `gateway_compressed_request_tcp_headers_and_near_limit` | 6 次原始 TCP 接收；唯一 CE／CL、wire 长度、旧 TE 清除与画像头名保留。解码精确 10 MiB 可发送；近上限 raw-deflate 入站不超限，标准 zlib 出站实际超过 10 MiB 仍成功，解码长度及 SHA256 与原逻辑字节一致。 |
| `gateway_compressed_request_auth_and_account_retries` | Messages／count_tokens 各两次 401 恢复发送，及 429 两账号换号；冻结 gzip,br 编码不漂移，实际身份、当前正文与 CCH 正确，不增加重试。 |
| `gateway_compressed_request_signature_stages_reencode_current_body` | 实际上游先后触发两次 signature 400，三次发送均为 gzip,zstd；ThinkingOnly 与 ThinkingAndTools 的独立结构断言及本次 CCH 均正确，各阶段逻辑正文确实改变。 |
| `gateway_compressed_request_does_not_retry_unsupported_upstream_encoding` | 上游 415 只发送一次并保留原 zstd 声明，无明文／其它编码回退。 |
| `gateway_compressed_request_cache_and_local_intercepts_are_equivalent` | 明文与 9 个编码样例共用一个逻辑缓存，只有首次业务上游发送，9 次 cache_hit 的 attempt_count 为零；prefill、warmup、Auto Mode 与后台状态 classifier 的本地结果等价，额外业务上游／Hello／RPM admission 为零。 |
| `gateway_compressed_request_read_errors_and_count_json_boundaries` | 两入口无编码／identity／gzip 的原始超限和 I/O 失败保留状态／错误形状；count_tokens 空体、数组、null、缺 model、空白 model 和非法 JSON 与明文拒绝结果一致。 |
| `gateway_compressed_request_router_authentication_precedes_decoding` | 真实 Router 的 4 路径 × 缺 token／无效 token／合法 token，先返回 401，合法 token 才进入编码声明 400；没有绕过入口鉴权。 |

通用非 JSON 的 `/artifact/publish` 是 loopback 合成样例，不代表新增真实 artifact 产品端点或放宽 v3 路径许可。既有 `/api/eval/test` 同样覆盖非 JSON 转发；产品端保留各入口原 JSON／非 JSON 行为。

### 既有回归与 transport 合同

- 最终全量同时通过既有 R2 根键过滤开关／请求快照、普通 Session／探针／池／Hello、beta 多值／query、stream 三态及 CCH／画像回归；新增链路只改变传输表示。
- `PreparedRequest` 元信息与 body 独立；Gateway 交给 `runtime_transport::send` 的已是最终编码 bytes。现有 send_direct、v3 内部发送和账号 sender 均按原字节转交；不新增编码字段，不改既有 128 MiB 内部接收上限或 `/v1/`、`/api/` 前缀许可。
- 最终全量的 `runtime_transport::tests::local_https_preserves_bytes_and_rejects_untrusted_or_wrong_hostname` 通过，实际验证 send_with_client 的 Vec 原字节、头顺序及证书／主机名边界；`tests/runtime_transport_test.rs` 的 3 项既有回归通过。压缩 CE／CL／原始 TCP 字节则由上述新增 Gateway 用例验证。

## 最终产品文件指纹

| 文件 | SHA256 |
| --- | --- |
| `src/service/gateway.rs` | `b48a8c0a3d265350260253bbba4e64cd25f503807d2ca00cc0474bdb10cba44d` |
| `src/service/mod.rs` | `5a75aeb822ac9ec362c523e94b457c6eb0fc8d49127d342fb015ea88c7fff96c` |
| `src/service/request_body_codec.rs` | `fbce6c6592e8d60800476f4ec2a2978825a907a2e7eb094f7f7452cc02e009bb` |

`Cargo.toml`、`Cargo.lock`、`src/service/rewriter.rs`、`src/service/runtime_transport.rs` 的 SHA256 与 `research/execution-baseline.json` 完全一致。没有修改响应解码／保活、TLS、画像常量、设置、前端、数据库或 bridge 协议，也未提交／推送。

## 限制与交接

- 上述网络证据均为本地合成 Gateway／TCP／HTTPS fixture，不是 300 之后的新原生抓包，不是实际 Anthropic 账号推理，也不保证远端接受每种 Content-Encoding。
- 4 层、32 片段、原始／各层 10 MiB、标准 br 与 zstd 16 MiB 窗口是明确支持边界；不是请求总内存硬上限，也不是可取消 CPU 超时。raw DEFLATE／Brotli 无通用内容 checksum，zstd checksum 可选。
- 本次没有启动生产账号容器、真实推理或 PostgreSQL 外部环境来补证据。v3 bytes 合同使用现有源码与既有测试证据，不声称完成生产 v3 压缩端到端验证。
- 产品文件已冻结，等待主会话独立 Check-All；任务生命周期、Spec 与提交／推送由主会话后续处理。
