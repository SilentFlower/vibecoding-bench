# Claude Code 官方协议抓包

> 用正式 vibecoding-bench 链路验证 Claude Code 版本、模型和权限模式的真实 wire 协议，并为 cc2api 版本画像提供可复核证据。

---

## 1. Scope / Trigger

以下任一情况必须执行本规范：

- 升级 Claude Code 版本、默认模型、Stainless runtime 或 billing/CCH 算法。
- Claude Code 新增权限模式、Auto Mode classifier、请求体字段、beta token 或 SSE 事件。
- cc2api 调整 `version_profile`、请求头/请求体改写、CCH、`cc_version` 或流式转发。
- 客户端出现网关兼容提示，或已有抓包与升级指南发生矛盾。

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
body: model, max_tokens, thinking, output_config, fallbacks, safeguards, thread
SSE: message_delta.delta.safeguard_results
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
4. 按首条 user message 最后一个 text block 和 JavaScript UTF-16 code unit 语义复算
   `cc_version` suffix；CCH 命中不能替代 suffix 验证。
5. 记录 `cc_entrypoint`、请求类型、模型、权限模式与 tool-use ID；核对
   `safeguard_results` 是否位于 `message_delta.delta` 并能关联同一 tool-use ID。
6. 单独识别 Haiku probe、title、bootstrap、telemetry 等辅助请求；它们不能被误判为 Auto classifier，
   也不能用主模型 beta 画像覆盖。

原始 `http_capture.jsonl`、`.flow` 和 Claude debug 只保存在受限远端目录，目录权限为 `0700`、
文件权限为 `0600`。仓库、任务文档与对话只保留脱敏摘要、run ID 和证据路径，不复制 token、完整
prompt、响应正文、组织 ID 或账号身份。

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
| 只有 Auto 出现 `safeguards` | 建立条件子画像，普通请求画像保持独立 |
| Plan 出现 `safeguards` | 按实际 body 与 beta 建立 Plan/Auto 共用或独立画像，取决于逐字段证据 |
| 模型不支持 Auto 且没有 safeguards | 记录为模型边界，不伪造或补齐 classifier 字段 |
| 抓包包含凭据或完整正文 | 仅在受限目录分析，不进入 Git、日志摘要或对话 |

---

## 5. Scenarios and Examples

**Normal**：同一账号和镜像先抓 Opus 的 `bypassPermissions`，冷却后抓 `auto`，逐请求复算 CCH 与
`cc_version`，再比较 beta/body/SSE；随后按相同节奏完成其余四种模式。

**Boundary**：Sonnet 在 `auto` 参数下没有 `safeguards`，但普通 beta 多出
`message-threads-2026-08-12`。这属于模型普通画像漂移，不能因为启动参数为 `auto` 就加入
`dangerous-tool-use` beta。

**Incorrect**：连续并发启动六个 run，用同一历史 `bypassPermissions` 样本做基线，并看到 CCH 值
不同后直接更换 seed。

**Correct**：单账号串行且间隔至少 120 秒；每个模型组先生成当前基线；CCH 对每条最终 body 独立
复算，只有算法在整组样本上稳定不命中时才研究 seed。

---

## 6. Tests Required

- API/DTO 测试覆盖六个合法 `permission_mode`、缺省 `bypassPermissions` 与非法值拒绝。
- scheduler、worker、continue 与 WebSocket resume 测试断言同一模式快照贯穿全链路。
- worker shell 静态测试断言六种值都通过校验，其他值在启动 Claude 前失败。
- WebUI 静态测试断言六个选项、缺省值、提交字段和详情展示。
- 抓包验收记录每个 run 的版本、镜像 tag、账号、代理存在性、模型、effort、权限模式、开始/结束时间、
  worker/sidecar 清理状态和受限证据路径。
- 协议分析必须输出逐请求 CCH 与 `cc_version` 复算结果、beta 有序差异、关键 body 字段和
  safeguards/SSE 对应关系；任一失败都不得标记画像已验证。
- cc2api 变更完成后运行 `cargo fmt --check`、`cargo test`、`cargo test cch`，并增加请求体未知字段
  保留与 `safeguard_results` 字节透传测试。
