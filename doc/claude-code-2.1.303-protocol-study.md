# Claude Code 2.1.303：vm2api 对照研究与后续抓包清单

核对日期：2026-10-28。本文记录当前源码和离线验证结果，为后续正式抓包提供观察清单；原版 303 的正式样本尚未在本次研究中采集。

## 1. 结论与证据范围

- vm2api 使用控制面组装请求、槽内改造过的 `cli-node` 最终发送的链路。它对部分入站标识执行白名单过滤，并使用自身的身份、billing 和缓存策略重建请求。
- 过滤按字段发生，不是以 `>= 2.1.300` 为条件拒绝整个请求；底层 CLI 仍可能生成自己的标识。
- vibecoding-bench 的完整 HTTP 记录能够保存新增请求头、响应头和正文，但轻量索引与自动 billing 摘要存在遗漏。查看索引没有某字段，不能据此判断客户端没有发送。
- 当前正式 HTTP 抓包产物不能证明原生 TLS 指纹与文章一致；需要补充客户端侧 ClientHello 证据。
- 本次只记录研究、复核现有采集代码和执行合成离线探针，没有修改协议实现、触发远程 capture run 或消耗真实账号额度。

核对基线：

| 仓库 | 路径 | 提交 |
| --- | --- | --- |
| vibecoding-bench | 本仓库 | `d944bbb57e51f550d8409bb686ef68cc80458308` |
| cc2api | `cc2api/`，独立 Git 仓库 | `d238aacb3a8ae430995f4742dfcd49b2df10e3fa` |
| vm2api | 同级目录 `../vm2api/` | `073a04ab6df836c9c3234839f28432503fc400b0` |

vm2api 的 CLI payload SHA256 为 `4975763790088a0eba226f20152b3c45261a0654b8bbc038701757b7699ab4e1`；kernel 为 `8a61aaa3cba06567a4c3b0039d357b341975e2495ec7fc7e8b5c3425cc53ec16`。结论与这些版本绑定，后续升级需要重新核对。

证据分为三类：

1. **当前源码事实**：函数、字段白名单、默认值及既有测试可直接复核。
2. **合成本地验证**：改造 CLI 到本地模拟上游，以及 recorder 的替身流测试；只能证明被测路径的行为。
3. **外部研究线索**：原作者对 303 的逆向记录；需要用正式原生抓包验证，不能作为本项目已验证画像或服务端风控结论。

本次可持久复核的脱敏结果保存在 [离线证据摘要](./claude-code-2.1.303-capture-evidence.json)。其中没有真实凭据、原始业务正文或真实账号标识。

## 2. 外部研究提到的观察点

主要来源为 [《Claude Code 2.1.303 逆向分析》](https://blog.xinrao.moe/article/3fe2c64d-9f79-80a5-b5cd-f429c899c952)。以下是待验证的字段语义，不推断服务端一定使用它们进行封禁或限流：

| 观察点 | 后续需要确认的内容 |
| --- | --- |
| `x-claude-code-wiggly-dove` | 环境与入口字典；核对开关、请求用途、字段结构及是否包含可读仓库标识 |
| `x-cc-atis` / `x-cc-atis-current` | 与 bootstrap `client_data.atis` 的关联，以及同会话固定、刷新后的变化 |
| `anthropic-dispatch-id` | 正常请求、自然发生的失败及重试之间的状态变化 |
| prompt-id、request-class、agent、compaction 相关头 | 逐轮关联，区分主会话、子代理、摘要压缩和辅助调用 |
| billing / suffix / CCH | 结合原始正文复算，避免把标识关联与内容校验混为一谈 |
| TLS ClientHello | 核对运行时变化、签名算法、key_share 与 ALPN；不能只比较 UA 或 JA3 |

官方文档确认 [gateway hint headers 的环境变量](https://code.claude.com/docs/en/env-vars) 从 2.1.273 起可用；[2.1.300 发布记录](https://github.com/anthropics/claude-code/releases/tag/v2.1.300) 也不等于上述所有字段的引入边界。因此不能把它们统称为“300 之后才有的拦截标记”。

## 3. vm2api 的具体处理

代码入口位于同级 vm2api 仓库的 `src/lib/identity/crs-headers.mjs`、`crs-persona.mjs`、`cch.mjs`，以及 `src/lib/transport/go-worker-client.mjs::finalizeWorkerPayload`。

| 项目 | 当前源码 / 本地样例确认的行为 | 不能外推的内容 |
| --- | --- | --- |
| `wiggly-dove` | 控制面白名单不接收；`test/unit/crs-headers.test.mjs` 明确断言过滤 | 不能据此证明底层 CLI 在全部远程开关条件下不会自行生成 |
| `atis` / dispatch | 控制面不透传，未找到相应缓存、会话状态或分发回退实现 | CLI 二进制内部在真实首方地址上的行为仍待确认 |
| prompt-id | 控制面不转发原值，槽位设置打开 `CLAUDE_CODE_GATEWAY_HINT_HEADERS=1`；本地最终请求生成了新值，与 billing 的 prompt-id 一致 | 本地自定义上游不覆盖官方地址与全部用途分支 |
| request-class、agent、部分 compaction 头 | 官方入站按条件白名单保留，不写入账号公共头文件；最终 CLI 仍可改写或生成 | 中间 envelope 白名单不等于最终 HTTP 逐头透传 |
| CCH | 控制面保留占位符，CLI 路径最后计算；已验证本地最终请求体与 CCH、Content-Length 一致 | CCH 一致不能证明其它环境字段或服务端决策一致 |
| TLS | 最终 HTTP 由槽内 CLI 执行，产物以 payload 二进制交付 | 仓库没有提供文章所述 303 ClientHello 的完整逐项验收证据 |

本地样例为 API Key、第三方入站、模拟上游：调用方传入 `request-class=auxiliary`，最终 CLI 发送 `subagent`；调用方 prompt-id 被替换；`wiggly-dove`、`atis`、dispatch 未出现。样例证明最终头需要实际观察，不能用 Node 对象代替。

### 3.1 与外部描述存在差异的行为

- `computeClaudeCodeFingerprint` 按 UTF-8 字节取样。文章描述 UTF-16 code unit；本地单文本中文样例中，vm2api 函数与最终发送值均为 `d98`，按文章索引规则为 `e9a`。ASCII `hello` 两者均为 `958`。差异已复现，是否偏离原版 303 必须再用原生样本判断。
- 自建 billing 的 prompt-id 关联出站会话，索引固定为 `cc_prompt_index=0`、`cc_turn_index=1`；代码注释说明这是为避免 system 前缀变化破坏缓存。
- `stripSubagentBilling` 删除首个 billing 行里的 `cc_is_subagent=true`，不因此删除正文中其它位置的示例。
- CCH 核心投影包括清空 model 值、处理 fallbacks / fallback_credit_token / max_tokens，再执行对应 hash；这些是最终字节规则，不能仅比较 JSON 对象或沿用另一版本的文本摘要。

## 4. 我们的 cc2api 当前状态

源码入口：[version_profile.rs](../cc2api/src/service/version_profile.rs)、[rewriter.rs](../cc2api/src/service/rewriter.rs)、[TLS 配置](../cc2api/src/tlsfp/tlsfp.rs)。

- 默认画像为 `2.1.293`，默认按入站 UA 选择已验证画像，默认允许版本截至 293；本次未新增 303 画像。
- 生成的 UA 使用 `(external, cli)`，新建 billing 使用 `cc_entrypoint=cli`。重写已有 billing 时保留调用方入口，因此仍可能带 `sdk-cli`。
- Stainless 当前默认已是 `0.128.0`，runtime 为 `v26.3.0`，这两个值相同不能代表 303 全面适配。
- 303 没有精确 CCH 画像；若直接把该版本传给底层函数，会进入未知版本投影和旧 seed 分支，不能只改版本常量上线。
- 当前 CC 请求头白名单不包含 wiggly、atis、dispatch、prompt-id 等调查项；请求类头仅有部分显式支持。
- 推理传输仍使用 `NODEJS_FINGERPRINT`，显式 key_share 为单个 X25519，需要与原生 303 ClientHello 独立对照。

后缀文本源还存在一项证据冲突：文章描述内部首个非元信息 user 的首个 text；本项目基于既有正式样本的 [画像规范](../.trellis/spec/cc2api/protocol/claude-code-profile-upgrade.md) 则取首条 user 最后一个 text，并对线程续轮复用已有后缀。新抓包应覆盖多文本块、中文 / emoji 和线程续轮，不能用文章覆盖已验证的旧版本规则，也不能直接外推到 303。

## 5. 现有抓包能捕获什么

已核对 [recorder.py](../images/sidecar/recorder.py)、[网络模式切换](../images/account/network-context.py)、[capture DTO](../orchestrator/main.py) 和 [请求级诊断说明](../cc2api/docs/request-diagnostics.md)。

| 信息 | 完整 `http_capture.jsonl` / `.flow` | `capture_index.json` / 页面摘要 | 当前结论 |
| --- | --- | --- | --- |
| 新增 HTTP 请求头 | 完整记录保存所有可见头，不按新增字段白名单过滤 | `cch_headers` 仅匹配 `cch / fingerprint / billing / anthropic` 头名 | 能采集；wiggly、atis、prompt-id 等可能不进索引 |
| 响应 `x-cc-atis-current` | 完整响应头保存 | 索引响应头主要保留 content-type | 需要从完整记录读取 |
| bootstrap `client_data.atis` | 完整响应正文保存；实际流必须经过当前 recorder | 索引不保存正文 | 能保存已发生的响应；热缓存会话未发 bootstrap 时不能补造 |
| system 文本中的 billing、CCH、额外字段 | 完整请求正文保存 | 当前 `_extract_analysis` 只解析同名 HTTP 请求头 | 原文能采集，自动 `cc_version` / `cc_entrypoint` 可能为空 |
| 重复头、头名大小写与顺序 | 优先保留 `.flow` 中的 header 列表进行核对 | 普通 dict 不保证完整表达重复头；索引更少 | 不能只用索引或 JSON dict 判定原始线序 |
| TLS 签名算法、key_share、JA3 / JA4 | JSONL 未输出 ClientHello；`.flow` 元数据不等于完整握手包 | 未提供 | 尚未形成正式采集与验收产物 |
| 未收到完整响应 / 中断的请求 | 请求阶段写 stats；完整 JSONL 在 `response()` 阶段写入 | 可能无对应完整条目 | 要核对 `.flow`、stats 和错误日志，不能认定缺字段 |
| cc2api 请求级诊断 | 只保存结构化摘要；不保存完整头、正文和握手 | 可关联画像、会话摘要、用量 | 可辅助定位，不能替代正式抓包 |

补充边界：

- `CAPTURE_MAX_BODY_BYTES=0` 表示不主动截断，仍应逐条检查 `body_truncated` 和采集错误。
- `_capture_body` 先获取 raw_content，但通常保存 `get_text(strict=False)` 解码后的 `body_text`；只有读取文本失败才写 `body_base64`。CCH 复算前应检查 Content-Encoding，并在需要时从 `.flow` 恢复、解压原始正文；不能将重新序列化的 JSON 当作原始字节。
- MITM 包含 CLI 到 sidecar、sidecar 到上游两段 TLS。出口处看到的 ClientHello 可能来自 mitmproxy。验证 CLI 原生握手必须确定采集点，另保留无解密透传条件的握手对照，并记录 MITM CA / 代理环境可能影响的行为。
- 旧每-run 链路的完整 capture 设置 `CAPTURE_SCOPE=all`；v3 的账号 context 应核对实际传入配置，不能只根据旧链路推断全站采样。Anthropic / Claude 目标域名在 recorder 默认范围内。
- 当前 `response()` 仍有目标流量判断，`CAPTURE_SCOPE=all` 本身不能证明任意第三方 host 都落入 JSONL。本文关注的官方 API / bootstrap 属于目标域名，但仍以实际 flow 为准。

### 5.1 本次离线验证

通过既有 `test_recorder` 的轻量 mitmproxy 替身，直接执行当前 `_capture_record` 和 `_capture_index_entry`，没有连接网络：

- 调查请求头全部保留在完整 request.headers；system billing、响应 atis 头与响应正文均保留。
- 未压缩 UTF-8 合成正文的 body_text 与输入逐字节相同，且未截断。
- system billing 未被自动 analysis 识别；atis、wiggly 未进入轻量索引；dispatch 因头名包含 anthropic 进入索引。
- 这些只验证当前采集函数的容纳能力，不证明原版 Claude Code 在真实条件下发送了对应字段。

## 6. 下一次正式抓包的观察清单

执行入口、串行间隔和模式矩阵仍遵循 [官方抓包规范](../.trellis/spec/vibecoding-bench/deploy/official-protocol-capture.md)，使用正式 `POST /api/captures/run`。下列内容是采样要求，不代表已经新增 API 参数或自动分析功能。

### 6.1 每个 run 固定记录

- Claude Code 版本与镜像 tag、Bun / Stainless 版本、账号和既有代理的脱敏标识、模型、effort、权限模式。
- 目标 host、入口、网络检查模式、MITM CA / 代理相关环境、是否沿用持久 HOME；记录远程开关信息的证据来源，未知值保持未知。
- 首次初始化 / 已缓存会话、是否实际出现 bootstrap、各阶段 flow_id 与相对时间。
- 正式采集路径、正文是否截断、请求是否完整终结；缺失值区分“没有发送”“被中间层过滤”“没有采到”“解析未覆盖”。

### 6.2 请求与响应逐项核对

1. 从完整 request.headers 盘点 wiggly、atis、dispatch、prompt-id、request-class、agent、compaction 等字段，保留大小写、重复项和顺序的证据来源。
2. 从 request.body_text 或原始 `.flow` 解码后的 JSON 查找 system 中的首个 billing 行，列出所有 key，分别验证后缀、CCH、入口和轮次；HTTP 同名头不存在不能算 billing 缺失。
3. 从完整 response.headers 观察 `x-cc-atis-current`，并关联同账号同会话的 bootstrap `client_data.atis`。研究报告仅保留是否存在、长度和哈希关联，不复制 token 原值。
4. 分别观察主会话、真实工具续轮、真实子代理、自然发生的压缩及辅助请求。某个用途未触发时记为“未覆盖”，不能用假头补出正式样本。
5. 对远端实验和 dispatch 仅观察自然出现的状态，不伪造服务端 token，不为制造回退而故意打错请求或制造上游错误。
6. suffix 同时比较候选文本源与 UTF-16 规则；CCH 独立使用目标版本投影与最终字节。两者任何一个命中都不能替代另一个。
7. 多轮比较缓存读写量及 system/tools/messages 前缀变化，区分协议一致性和缓存收益。

### 6.3 TLS 补采要求

- 使用能够保留客户端到 sidecar 这一段原始 ClientHello 的旁路采样或等价取证方式；记录接口、方向、目标、连接与 run 的关联。
- 比较签名算法、有序扩展、supported_groups、key_share 的组与数量、ALPN、会话恢复；JA3 与 JA4 均只是摘要。
- 独立保留同版本无解密透传的对照，确认 MITM / CA / 环境变化是否影响客户端请求或握手。
- 当前 API / recorder 没有把这些信息变成正式产物。先设计最小补采与脱敏存储，再实施；本文不宣称已经补齐。

### 6.4 接受与拒绝结论

| 观察结果 | 可以写入的结论 |
| --- | --- |
| 正式 flow 中有新增头，索引没有 | 采集到了，摘要未覆盖 |
| 对照条件明确、原始 flow 完整，某头始终缺失 | 只描述该版本、用途、账号开关及采集条件下未发送 |
| 只在 vm2api / cc2api 出口缺失 | 检查过滤与重建，不直接推断原生行为 |
| 全部正式正文可复算 CCH，suffix 也独立通过 | 对已覆盖场景标记规则验证通过；不外推未覆盖模型和分支 |
| 只有 MITM 出口 JA3 / JA4 | 不能作为原生 CLI TLS 画像 |
| 没有观察到 bootstrap 或相关功能分支 | 保持未覆盖，安排后续自然采样 |

## 7. 后续实施边界

本次没有改 recorder、请求头白名单、CCH 或版本画像。后续若实施增强，优先拆为可独立验收的范围：

1. 离线分析完整记录中的 system billing、条件头与 bootstrap 关联，补充不会泄露 token 的摘要；先复用现有原始文件。
2. 捕获新头但不预设固定值，按请求用途、地址及会话生命周期记录观察事实。
3. 单独为 TLS 增加客户端侧握手证据及对照，避免把 HTTP 抓包能力等同于 TLS 保真。
4. 正式 303 样本通过后，再评估 cc2api 的独立版本画像与传输配置；不能只升级 UA 版本或复制 vm2api 的过滤策略。
