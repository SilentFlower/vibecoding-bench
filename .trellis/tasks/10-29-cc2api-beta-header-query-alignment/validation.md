# R3-02／04 实施验证记录

日期：2026-10-29。Rust 验证工作目录：`/root/project/vibecoding-bench/cc2api`。

## 实施与交接基线

- 已确认 Brief 后按主会话派工实施，实际产品改动仅在 `cc2api/src/service/gateway.rs`：beta 专用多值合并、目标路径 beta query 归一；复用已有合并函数，没有新增依赖、设置或 fixture 文件。
- cc2api HEAD 为 `0bcec9d70f5af738034045d288f9511bc723ac21`。R2 九文件清单 `/tmp/r2-session-fbk001-source-sha256.txt` 校验全部通过，其 SHA256 为 `67d71f6acc39f4f1acf63ab287529227326e3d5b7804b4cea7d881f9fdab1969`。
- 实施前 Gateway 备份：`/tmp/r3-beta-header-query-before-gateway.rs`，SHA256 为 `71f2808e05fe213ed6b57953de4b0ad49d86a3073437f2117ac5108db2646312`。其余八个交接文件在实施后继续逐项匹配 R2 原值。

## 命令、退出码与红绿证据

日志目录：`/tmp/r3-beta-header-query-validation/`；`commands.jsonl` 记录每次格式化／测试的工作目录、完整参数、起止时间、退出码和对应 Gateway 指纹。

| 阶段 | 命令 | 退出码 | 结果 | 日志文件 |
| --- | --- | --- | --- | --- |
| 旧逻辑红灯 | `cargo test --locked gateway_beta_ -- --nocapture` | 101 | 0 通过／2 失败，均在实际 Gateway 出站断言失败 | `red-gateway-beta.log` |
| 最小修复绿灯 | 同上 | 0 | 2 项通过，76 次合成出站 | `green-gateway-beta-initial.log` |
| 完整专项 | 同上 | 0 | 6 项通过，175 次合成出站 | `green-gateway-beta-matrix.log` |
| 最终格式 | `cargo fmt --check` | 0 | 通过 | `format-check.log` |
| 最终全量 | `cargo test --locked` | 0 | **717 通过／0 失败／3 既有 PG 忽略** | `full-rust-tests.log` |
| CCH 回归 | `cargo test --locked cch` | 0 | **40 通过** | `cch-regression.log` |

红灯的首个 header 断言实际收到 `client-second` 在 `client-first` 前，证明后行覆盖了首次顺序；query 断言实际收到 `beta=false&beta=true`，期望为唯一 `beta=true`。红灯 Gateway SHA256 为 `4fa9fafe9ebf94b95c82a7310f7adb956ab21306b0caaa0b0f311f2be2e01cfc`，测试增量保存于 `red-tests-only.patch`。完整专项运行时 SHA256 为 `9ca9aaef11afb316408a94c46907d49b39d891412cbe3b455b2ae4235380f863`；随后仅调整测试导入并扩展既有 count_tokens URL 断言，最终全量与 CCH 使用下方最终指纹。

全量分组通过数为 lib 649、account_scheduler 33、account_store_timestamp 15、gateway_429_retry 6、http1_header_casing 4、redis_url 6、runtime_transport 3、version_profile_settings 1。三项忽略继续要求专用 PostgreSQL 测试 DSN；本轮未配置。既有 vendor／依赖编译警告未扩展修复。

## 实际上游覆盖矩阵

观察点是 loopback 上游处理器实际收到的 `HeaderMap`、body 字节和 `Uri`；`Uri.query()` 直接比较完整原始 query，没有使用 query 解码器替代。`duplicate_beta_request` 先移除 `profile_request` 自动 beta，再以 `HeaderMap::append` 构造同名多值及大小写头名。

| 测试名后缀（均为 `gateway_beta_`） | 出站数 | 覆盖 |
| --- | --- | --- |
| `headers_merge_before_account_filters` | 16 | 280／293 × 1M／Fast 开关 × 两行交换；重叠、空段、空白、相似日期、相似 Fast token、已知画像顺序与首次顺序、唯一出站 beta；交换行不改变 body，最终 CCH 有效 |
| `headers_preserve_empty_invalid_and_single_value_semantics` | 11 | 缺头、有效空头、全非法、非法与有效／空值互换、重叠；Registry 实际区分空头与缺头；普通／count_tokens 的 UA、request-id、客户端 request-id、Authorization 保留原单值和过滤策略 |
| `count_tokens_merges_before_account_filters` | 24 | 280／293／API × 1M／Fast 开关 × 两行交换；保留专用 token-counting，包含 fallbacks 也不引入生成用 fallback beta；实际固定 URL 仍只有 `?beta=true`，不保留客户端附加 query |
| `headers_preserve_special_and_api_profiles` | 48 | 293 Auto／Plan safeguard、标题 CC／API、1M／Fast 四组合、两行交换；280／293 API 普通生成不扩大客户端 beta；293 eval／MCP／penguin 后台窄表保持精确值 |
| `query_normalizes_keys_and_preserves_raw_fragments` | 60 | 280／293／API × 20 种 query：缺省、空、true／false、裸键、重复混合、一次编码同名键、畸形／双重编码、大小写相似键、加号／编码分隔符、空片段、其它参数编码与重复值、合成未知键保真；query 不改变 body |
| `query_preserves_non_target_paths` | 16 | 280／293 × 8 个非目标／近似路径，完整 query 原片段不变 |

既有 URL 单测另覆盖通用 URL 构造器的精确 count_tokens 路径与编码 beta 冲突。最终全量同时通过 R2 根键清理 Gateway 8 项、Session Gateway 5 项（含 FBK-001 首尾 SP／HTAB、探针和池优先级）、实际 stream 三态 1 项及其它 Rewriter／CCH 回归。

前端未改，复用 R2-03 已通过的 `cd web && npm run build`；已核验 `/tmp/r2-top-field-web-build.log` SHA256 仍为 `1ea9756a58b90acf9381e163601fd0afa91d07354eb123490d365a8ac9e4564e`，没有重复构建。

## 最终源码与独立增量

九文件清单：`/tmp/r3-beta-header-query-source-sha256.txt`，SHA256：`1aa7cf1ce4762ddfe980e571312f665bd62af2792a11e24c2b7a280a08dc591b`。以下路径均相对 cc2api：

```text
c9c5577553e392d9ec2258cecc8505ff0db7b35692f066546cd447ed997ded19  README.md
5438b04b893c3122db2dd6c733d65bf97210296c2786c30abf8183befdfdce4d  src/handler/router.rs
033075b5674b373b15960e2fafdd2cee8ba94303790fd9a7e59b5aeeb35facae  src/main.rs
aac55d0dd4ffd7a5cd45af8cb0f6838e33e67ab83c2bea7efb073c4ee11158c6  src/service/gateway.rs
9375be4439d99d502d8263372e65028d8407eb28e408e686a31d4c3bdfc5b309  src/service/rewriter.rs
10b028eabdd3f2d2cdb8b810493c73cdbca92359f8d8e5745ecf5f90b653d08c  src/store/db.rs
0c7285cfa626eb0e8f7dee2e994ec86ef79e74291827a871e0186831a4db172d  src/store/settings_store.rs
77b03053712038bd63a1551a2556f5ceb5e5ccea4616b48170c92e3a6945bd6f  tests/fixtures/messages-top-field-drop-keys.json
5cbaf56788dd19d2f8e44404ae8eb37efb74a2295b10e65b399719210b970ccf  web/src/components/Settings.vue
```

相对 R2 Gateway 备份的独立增量为 `/tmp/r3-beta-header-query-independent.patch`，增加 730 行、删除 18 行，主要为六项实际 Gateway 回归和捕获助手；SHA256 为 `e905ab9212790a3061b9e5c122068dc02c1b854b4dc89b14800b4d34ab300dc2`。测试证据 SHA256：

```text
53f6bd5719e3bfb18db7dc01408d87eab5331f682ed96910d2cf72fc1ef32b3e  red-gateway-beta.log
cea6a798b125fc8eff1dde1377e6d195e4e4d1dd7c13043be69b3c8cbe65e930  green-gateway-beta-matrix.log
57f057a798db2cb2b326404d22f133690abce75ff998798dec6094b03c490d29  full-rust-tests.log
5e342e15d665c1c38af1975c113fc69ec95627daaa7eabbb5f4c88a5c1faa08d  cch-regression.log
0b419ce9ce8572196b825fa81e1581c85c2794bacb9ac06847cdbc62806e0049  commands.jsonl
```

## 验证边界与移交

仅使用合成 loopback 上游，没有真实账号推理、远端修改或新抓包读取；mock 的 200 不证明官方接受这些参数。沿用已冻结的 592 条原生 query 研究，不声称新读取 293 原件。没有浏览器验证或 PostgreSQL 实跑；没有 Git add／commit／push。

实现与验证完成，产品源码已冻结，无遗留已知失败。仅更新本任务 `implement.md` 与本记录；Phase 2.1、Check-All、Spec 和 Push 由主会话继续。
