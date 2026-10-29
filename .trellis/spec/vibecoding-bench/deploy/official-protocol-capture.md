# Claude Code 官方协议抓包

> 用正式 vibecoding-bench 链路验证 Claude Code 版本、模型和权限模式的真实 wire 协议，并为 cc2api 版本画像提供可复核证据。

---

## 1. Scope / Trigger

以下任一情况必须执行本规范：

- 升级 Claude Code 版本、默认模型、Stainless runtime 或 billing/CCH 算法。
- Claude Code 新增权限模式、Auto Mode classifier、请求体字段、beta token 或 SSE 事件。
- cc2api 调整 `version_profile`、请求头/请求体改写、CCH、`cc_version` 或流式转发。
- 客户端出现网关兼容提示，或已有抓包与升级指南发生矛盾。
- `/v1/messages` 经 new-api 等中间网关转发，且 Claude Code 新增请求字段或流式事件。

协议事实只能来自正式 capture API 创建的 run。链路固定为：

```text
POST /api/captures/run
  -> orchestrator scheduler
  -> worker（目标 Claude Code 版本）
  -> sidecar MITM
  -> 账号既有 upstream proxy
  -> api.anthropic.com
```

宿主机直连、手工 HTTP 请求、临时 worker、绕过账号代理或经 `jp.ai.flower-cli.com` 产生的流量不得作为官方基线。

---

## 2. Signatures

抓包 API：

```text
POST /api/captures/run
account_id: int
topic_id: int
prompt: string | null
prompt_mode: "natural" | "canonical"
timeout_sec: int
model_override: string | null
claude_code_version: string | null   # 单次精确版本，留空继承账号及全局
effort_level: "low" | "medium" | "high" | "xhigh" | "max" | null
permission_mode:
  "manual" | "acceptEdits" | "plan" | "auto" | "dontAsk" | "bypassPermissions"
```

运行身份与 worker 边界：

```text
runs.claude_code_version
runs.claude_effort_level
runs.capture_permission_mode
worker env: CLAUDE_CODE_VERSION, CLAUDE_CODE_EFFORT_LEVEL, CLAUDE_PERMISSION_MODE
Claude CLI: claude --permission-mode <mode> --model <model>
```

证据目录：

```text
data/flows/<account>/<topic_id>/<run_id>/
├── capture_index.json
├── http_capture.jsonl
├── stats.jsonl
└── *.flow
```

关键 wire 字段：

```text
User-Agent
X-Stainless-Package-Version
X-Stainless-Runtime
X-Stainless-Runtime-Version
anthropic-version
anthropic-beta
x-anthropic-billing-header:
  cc_version=<version>.<suffix>; cc_entrypoint=cli; cch=<5hex>;
body: model, max_tokens, thinking, output_config, diagnostics, fallbacks, safeguards, thread
SSE: message_delta.delta.safeguard_results
```

中间网关核对点（只用于与官方基线对照，不作为官方抓包链路）：

```text
Claude Code -> new-api -> cc2api -> Anthropic
new-api: relaykit/dto/claude.go::ClaudeRequest
new-api: relay/helper/valid_request.go::GetAndValidateClaudeRequest
new-api: relay/claude_handler.go::ClaudeHelper
```

---

## 3. Contracts

### 3.1 基线与矩阵

- 每次升级都重新抓当前版本的 `bypassPermissions`，不得沿用历史版本或历史镜像的样本。
- Auto Mode 协议验证必须至少成对抓取同版本、同主模型、同 effort 的
  `bypassPermissions` 与 `auto`，并逐字段比较。
- 主模型覆盖 Claude Code 当前暴露的全部权限模式：`manual`、`acceptEdits`、`plan`、
  `auto`、`dontAsk`、`bypassPermissions`。
- `plan` 是 classifier 重点分支：当 Auto Mode 可用且 `useAutoModeDuringPlan` 保持默认开启时，
  Claude Code 会让 classifier 审核规划阶段的 shell 命令，不能把 Plan 当成普通只读对照。
- 次要兼容模型至少抓 `auto` 与 `plan`。若 beta、body 或 SSE 与主模型不同，立即扩展为六模式，
  不从模型名称或官方支持表外推协议。
- 提示词使用语义相近的自然工程任务，并诱发安全、可复核的工具调用；不得提及抓包、classifier、
  `safeguards`、beta、权限模式或测试目标。不同 run 可以轻微改写措辞，分析时不得用 CCH 字面值相等
  代替算法复算。

### 3.2 限频与运行隔离

- 同一账号同时只允许一个正式抓包 run；全局也按串行执行，不并发启动矩阵样本。
- 只有前一 run 进入终态、对应 worker/sidecar 已清理且日志没有继续重试后，才能启动下一 run。
- 相邻 run 启动时间至少间隔 120 秒。出现 `429`、连续 `5xx`、上游 retry 或账号限额变化时，停止矩阵至少 15 分钟并重新查询账号状态；不得自动换账号继续突发请求。
- 固定 Claude Code 版本、worker/sidecar 镜像 tag、账号、代理出口、模型、effort、topic 与 capture 配置。
  必须更换账号时，从新的 `bypassPermissions` 基线重新开始该模型组。

### 3.3 每条主请求的漂移复核

每条 `/v1/messages?beta=true` 都独立检查，不能只抽第一条：

1. 核对身份头、`anthropic-beta` 的完整 token 集合与顺序。
2. 核对顶层 key 顺序，以及 `model`、`max_tokens`、`thinking`、`output_config`、`fallbacks`、
   `safeguards`、`thread` 的存在性与结构。
3. 按该请求最终 body 字节和目标版本规则复算 CCH。先使用升级指南记录的 seed；只有全部样本都不命中，
   才能研究 seed 变化。
4. 初始请求按首条 user message 最后一个 text block 和 JavaScript UTF-16 code unit 语义复算
   `cc_version` suffix；存在 `thread.previous_message_id` 的续轮校验三位小写十六进制形状与
   同 run 稳定性，即使当前消息重新出现 text block 也不得按该文本复算。网关改写时应保留入站
   billing block 的会话后缀。CCH 命中不能替代 suffix 验证。
5. 记录 `cc_entrypoint`、请求类型、模型、权限模式与 tool-use ID；核对
   `safeguard_results` 是否位于 `message_delta.delta` 并能关联同一 tool-use ID。
6. 单独识别 Haiku probe、title、bootstrap、telemetry 等辅助请求；它们不能被误判为 Auto classifier，
   也不能用主模型 beta 画像覆盖。

原始 `http_capture.jsonl`、`.flow` 和 Claude debug 只保存在受限远端目录，目录权限为 `0700`、
文件权限为 `0600`。仓库、任务文档与对话只保留脱敏摘要、run ID 和证据路径，不复制 token、完整
prompt、响应正文、组织 ID 或账号身份。

### 3.4 中间网关请求体保真

- 官方直连抓包是字段基线；经 new-api 的业务链路应在每一跳比较 `/v1/messages` 的顶层 key
  集合、字段 JSON 类型及嵌套值。只比较 `safeguards` 不足以发现其他字段被 DTO 丢弃。
- Claude Code 2.1.280 的 20 条本地辅助样本中，`diagnostics` 出现 10 次，`fallbacks`
  出现 2 次，`thread` 出现 2 次；它们只用于排查中间网关丢字段，不能代替正式抓包基线。
  正式 Auto/Plan 抓包另确认 Opus 5.5/4.8 的 `safeguards`。样本频次不是后续版本或其他
  模型的允许字段清单。
- `diagnostics` 是对象，样本键为 `previous_message_id`（字符串或 `null`）。它让上游比较前一
  响应与当前请求的提示词缓存指纹，返回缓存未命中原因；丢失它会关闭该请求的诊断记录。
  cc2api 的 Haiku 主请求 beta 画像也会按该字段是否存在分支。详见
  [官方缓存诊断文档](https://platform.claude.com/docs/en/build-with-claude/cache-diagnostics)。
- `fallbacks` 样本值为字符串 `"default"`；协议还允许指定回退模型列表。它请求在安全策略拒绝
  后由服务端选择后备模型，并须与相应 `server-side-fallback-*` beta 一起核对；它不是限流或
  过载重试开关。cc2api 对其存在性有 beta 规则，CCH 规则也随版本变化。详见
  [官方拒绝与回退文档](https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback)。
- `thread` 样本为 `{"type":"request"}`；已验证的 2.1.280 续轮可增加
  `previous_message_id`。其会话续接用途由抓包形态与 cc2api 的续轮后缀逻辑推断，不把公开
  文档尚未确认的服务器行为写成保证。丢失 `thread.previous_message_id` 会使 cc2api 无法按
  续轮规则复用入站 `cc_version` 后缀；`message-threads-*` beta 仍以实际请求头为准。
- 普通 new-api Claude 渠道会把请求反序列化为 `ClaudeRequest` 再序列化；DTO 未声明的顶层
  字段会消失。全局或渠道请求体透传开启时使用原始 body。无论选择哪种路径，升级时都要
  逐字段核对实际转发结果；已声明字段的未知嵌套内容应原样保留，不能凭字段名自行补值。

### 3.5 条件标识、正文归因与 TLS 的采集边界

- 核对 303 等新版本时，从完整 `http_capture.jsonl` 的 `request.headers` 盘点
  `x-claude-code-wiggly-dove`、`x-cc-atis`、`anthropic-dispatch-id`、
  `x-claude-code-prompt-id`、`x-claude-code-request-class`、agent 与 compaction 相关头。
  记录版本、入口、请求用途、地址、权限模式及开关证据；条件未覆盖记为未知，不补造头值。
- bootstrap 实际发生时，将响应正文 `client_data.atis` 与后续请求 `x-cc-atis`、响应
  `x-cc-atis-current` 按账号和会话关联。研究产物仅保留存在性、长度和哈希关系；不复制
  opaque token 原值。持久 HOME 命中缓存、没有 bootstrap flow 时，不能断言 token 不存在。
- `images/sidecar/recorder.py::_capture_record` 保存完整请求/响应头与正文；
  `_capture_index_entry` 只保存子集，`analysis.cch_headers` 按头名正则
  `cch|fingerprint|billing|anthropic` 筛选。索引缺少 wiggly、atis、prompt-id 等值不能说明
  客户端未发送。`_extract_analysis` 当前只解析同名 HTTP billing 头；system 文本中的
  `x-anthropic-billing-header:` 必须从完整请求正文另行提取，不能把空摘要当作归因缺失。
- `body_text` 经 `get_text(strict=False)` 解码，`body_base64` 是文本读取失败时的回退；
  复算前检查 `body_truncated` 和 Content-Encoding，需要时从 `.flow` 恢复并解压原始内容。
  重复头与头名线序优先核对 `.flow`，不能只使用普通 dict 或重新序列化后的 JSON。
- HTTP JSONL 按事件追加：请求体可读时为 `capture_state=pending`，响应完成为 `complete`，
  连接错误或 Recorder 停止为 `interrupted`。同一 flow 可能有多条阶段记录，索引按 flow_id
  保留最新状态；停止后迟到 response 可以补写已收到字节，但不能覆盖中断事实。无完整响应时，
  结合 `.flow`、stats、`capture-status.json` 和采集错误判断保存范围。
  `CAPTURE_SCOPE=all` 不免除当前 `response()` 的目标域名判断；
  v3 也须检查实际账号网络 context，不能只套用旧每-run sidecar 的 scope 默认值。
- 开启完整抓包后，Recorder 在客户端 `tls_clienthello` 保存私有 `tls_clienthello.jsonl`，
  含 ClientHello 本体、有序扩展／算法／组／key_share 和 JA3；字节封装、版本／执行／HTTP 连接关联、
  私有文件与安全摘要遵循 [ClientHello 契约](../backend/account-runtime-v3.md#scenario-客户端-clienthello-私有证据与安全摘要)。
  JA4 未实现；历史 `.flow` 的部分 TLS 元数据不能替代新握手。MITM 出口可能来自代理，不能当作
  原生 CLI offer；执行版本也不能独自证明发起进程。正式 TLS 对齐仍需关联实际 Claude HTTP，
  标明接口、方向、目标与运行条件，并与相同版本无解密透传条件对照。
- vm2api 改造 CLI 对本地模拟上游的结果和外部逆向文章只作为研究线索，不直接写成原版 303
  的正式画像。后缀文本源、Unicode 取样和线程续轮规则有冲突时，沿用旧版本已验证契约，
  对新版本单独安排正式样本。详见 [303 对照研究与采样清单](../../../../doc/claude-code-2.1.303-protocol-study.md)。

---

## 4. Validation & Error Matrix

| 条件 | 处理 |
|------|------|
| 请求未走正式 orchestrator/worker/sidecar/账号代理链路 | 样本无效，删除分析结论并按正式链路重抓 |
| `bypassPermissions` 使用历史样本 | 样本无效；以当前镜像、版本和账号重新抓基线 |
| run 仍在执行或容器未清理 | 不启动下一 run |
| 相邻 run 小于 120 秒 | 延迟启动，保持串行窗口 |
| 出现 `429`、连续 `5xx` 或 retry | 暂停至少 15 分钟，重新查额度与账号状态 |
| 账号或代理出口中途变化 | 当前模型组失去可比性，从新账号的新基线重启 |
| CCH 字面值与另一 run 不同 | 先按各自最终 body 复算；不得直接判为 seed 漂移 |
| CCH 命中但 `cc_version` 不命中 | 独立检查 suffix 文本源、UTF-16 索引、版本和 header 格式 |
| 线程续轮带 text 但确定性 suffix 不命中 | 检查 `thread.previous_message_id`；存在时验形并检查同 run 后缀稳定性 |
| 只有 Auto 出现 `safeguards` | 建立条件子画像，普通请求画像保持独立 |
| Plan 出现 `safeguards` | 按实际 body 与 beta 建立 Plan/Auto 共用或独立画像，取决于逐字段证据 |
| 模型不支持 Auto 且没有 safeguards | 记录为模型边界，不伪造或补齐 classifier 字段 |
| 官方请求有字段而中间网关出站缺失 | 检查 DTO/透传设置，修复后按同一模式重放；不得把缺失字段解释成客户端未发送 |
| `diagnostics` 丢失或 `fallbacks` 与 beta 不匹配 | 分别核对缓存诊断与服务端回退契约，再检查 cc2api 的 Haiku beta、fallback beta/CCH 画像 |
| 续轮 `thread.previous_message_id` 丢失 | 核对各跳 body 与入站 `cc_version` 后缀，不按当前 user text 重算续轮后缀 |
| 完整 HTTP 有条件头但索引没有 | 认定摘要未覆盖，从完整记录继续分析，不补造字段 |
| system 有 billing 而 analysis 为空 | 从原始 system 提取并复算，不按 HTTP 同名头是否存在判断 |
| 仅取得 MITM 出口握手或 JA3 | TLS 原生画像未验证；补客户端侧 ClientHello 与透传对照 |
| 抓包包含凭据或完整正文 | 仅在受限目录分析，不进入 Git、日志摘要或对话 |

---

## 5. Scenarios and Examples

**Normal**：同一账号和镜像先抓 Opus 的 `bypassPermissions`，冷却后抓 `auto`，逐请求复算 CCH 与
`cc_version`，再比较 beta/body/SSE；随后按相同节奏完成其余四种模式。

**Boundary**：Sonnet 在 `auto` 参数下没有 `safeguards`，但普通 beta 多出
`message-threads-2026-08-12`。这属于模型普通画像漂移，不能因为启动参数为 `auto` 就加入
`dangerous-tool-use` beta。

**Boundary**：Sonnet 线程续轮在 `tool_result` 后重新带入 text block，但只要请求包含
`thread.previous_message_id`，`cc_version` 仍复用会话级三位后缀；不得把当前 text 当作确定性来源。

**Incorrect**：连续并发启动六个 run，用同一历史 `bypassPermissions` 样本做基线，并看到 CCH 值
不同后直接更换 seed。

**Correct**：单账号串行且间隔至少 120 秒；每个模型组先生成当前基线；CCH 对每条最终 body 独立
复算，只有算法在整组样本上稳定不命中时才研究 seed。

**Incorrect**：只在 new-api DTO 中补 `safeguards`，就认定新版本全部请求字段已透传。

**Correct**：先从官方抓包提取每条请求的顶层 key 与关键嵌套字段，再逐跳比较；对
`diagnostics`、`fallbacks`、`thread` 和以后新增的字段，检查值、类型、beta 配对与续轮行为。

---

## 6. Tests Required

- API/DTO 测试覆盖六个合法 `permission_mode`、缺省 `bypassPermissions` 与非法值拒绝。
- scheduler、worker、continue 与 WebSocket resume 测试断言同一模式快照贯穿全链路。
- worker shell 静态测试断言六种值都通过校验，其他值在启动 Claude 前失败。
- WebUI 静态测试断言六个选项、缺省值、提交字段和详情展示。
- 单次版本控件必须属于 `capture-form`；浏览器覆盖显式版本、账号继承和全局兜底的提交、成功清空及详情打开。确认没有错误弹窗、没有配置写请求，批次表单不能误含抓包专用字段。
- 抓包验收记录每个 run 的版本、镜像 tag、账号、代理存在性、模型、effort、权限模式、开始/结束时间、
  worker/sidecar 清理状态和受限证据路径。
- 协议分析必须输出逐请求 CCH 与 `cc_version` 复算结果、beta 有序差异、关键 body 字段和
  safeguards/SSE 对应关系；任一失败都不得标记画像已验证。
- 验收条件头时逐条对照完整 request/response 与轻量索引，覆盖 system 内 billing、bootstrap
  `client_data.atis` 的脱敏关联、采集截断和无完整响应；合成离线探针只能证明采集函数能力。
- 若实施 TLS 补采，须覆盖客户端侧与 MITM 出口方向区分、signature_algorithms、key_share、
  ALPN 及无解密透传对照；没有握手产物时不得将 HTTP 检查通过报告为 TLS 指纹通过。
- 经过 new-api 时，DTO 往返测试须断言 `safeguards`、`diagnostics`、`fallbacks`、`thread`
  及未知嵌套字段不丢失；逐跳回归须比较实际出站 JSON，不能仅检查 Go 字段声明。
- cc2api 变更完成后运行 `cargo fmt --check`、`cargo test`、`cargo test cch`，并增加请求体未知字段
  保留与 `safeguard_results` 字节透传测试。
