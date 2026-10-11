# Claude Code 2.1.293 正式抓包进度

## 最新复核

- 用户截图澄清：默认画像改为 293，通过允许范围 `2.1.89-2.1.293` 和禁止范围 `2.1.89-2.1.279,2.1.281-2.1.292` 使 Claude Code/CLI 实际仅允许 280、293；保留 260 画像、映射和选项，不新增针对 260 的强制迁移。非 Claude 客户端继续遵守已有 UA 白名单。
- 最终复核时间 1791444041.6089394：完成 25 轮、112 条 billing，CCH 和响应关联的会话后缀全量独立复查全部通过；正式链路、版本、镜像、canonical 文本、终态清理、串行和工具关联全部通过，最小启动间隔为 184.50871348381042 秒。
- 四模型六模式齐备，没有待采集轮次。最终受限权限检查覆盖 75 个目录、300 个文件，偏差为零；控制器已退出，权限守护核对归属后终止，未中断其它任务。
- 最终报告为 capture-matrix-audit.json、protocol-contracts.json、capture-final-recheck.json；以下交接记录保留当时快照。
- 最终 beta 比对确认 Haiku 普通主请求有省略 claude-code 的分支，Plan 有省略 extended-cache-ttl 的分支。按原生客户端实际 beta 保留选择及位置，不把 mode/thread 作为未经验证的推断规则。


## 用户约束

- 只使用线上完整 HTTP 抓包任务和既有题库默认文本，`prompt=null`、`prompt_mode=canonical`；不人工续写或添加提示词。
- 串行、相邻启动至少间隔 120 秒、前一 run 终态且容器清理后再开始下一轮。
- 账号按模型组轮换，换账号重新抓 bypassPermissions 基线；等待账号空闲，不中断既有养号。
- 本轮重点为 Opus 5.5、Sonnet 5.5、Haiku 5.5，以及用户追加的 Fable 5.1；旧 Sonnet 5、Haiku 4.5 不单独追加任务。

## 受限远端证据

- 根目录：`/root/vibecoding-bench/.capture-audits/293-20261008-codex-f2c4/`。
- 原始 `.flow`、`http_capture.jsonl` 和运行记录仅保留远端，目录 0700、文件 0600。
- `capture-controller.py` 仅为本次运维控制脚本，不修改 orchestrator、worker 或 cc2api 产品代码。
- `controller-state.json` 记录当前 run、完成集合、剩余矩阵、等待原因和异常冷却；控制器设置两小时上限。
- 初始计划 19 个短窗口。追加 Fable 后，先增加 baseline/auto/plan 三轮；实际差异触发额外 manual/acceptEdits/dontAsk，至多 25 个窗口。后续顺序为账号 22 的 Fable、账号 15 的 Haiku、账号 22 的新 Opus 基线组；保留原控制器截止时间，超时后记录剩余项。
- 单轮超时 240 秒，首轮为 300 秒。达到至少 150 秒并取得三个主响应，或已取得主响应而等待人工权限时，可通过正式 stop API 收口；停止不额外输入 prompt。
- HTTP 429、同端点连续 5xx、上游重试或 quota 门禁触发时停止矩阵，并记录至少十五分钟冷却。账号轮换不能跳过冷却。

## 当前已验证样本

| run ID | 账号 ID | 模型 | 权限模式 | 状态 | billing | CCH 命中 | 后缀命中 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `76f9af2285bc` | 22 | `opus[1m]` 实际为 `claude-opus-5-5` | bypassPermissions | success | 8 | 8 | 8 |
| `a474f354b4a5` | 22 | `opus[1m]` 实际为 `claude-opus-5-5` | auto | stopped（采够后收口） | 5 | 5 | 5 |
| `b9d2c6b0fa12` | 22 | `opus[1m]` | plan | stopped（采够后收口） | 5 | 5 | 5 |
| `9a10fc90dd5c` | 15 | `claude-sonnet-5-5` | bypassPermissions | stopped（采够后收口） | 4 | 4 | 4 |
| `e07bd35e26dd` | 15 | `claude-sonnet-5-5` | auto | stopped（采够后收口） | 4 | 4 | 4 |
| `35134f910520` | 15 | `claude-sonnet-5-5` | plan | timeout（题库任务未完成） | 3 | 3 | 3 |
| `796c212dedaa` | 15 | `claude-sonnet-5-5` | manual | stopped（采够后收口） | 4 | 4 | 4 |
| `fa81f4358769` | 15 | `claude-sonnet-5-5` | acceptEdits | timeout（题库任务未完成） | 2 | 2 | 2 |
| `f178d830d414` | 15 | `claude-sonnet-5-5` | dontAsk | stopped（采够后收口） | 5 | 5 | 5 |
| `8b9029853425` | 22 | `claude-fable-5-1[1m]` 实际为 `claude-fable-5-1` | bypassPermissions | stopped（采够后收口） | 5 | 5 | 5 |
| `5e7d7cf30b69` | 22 | `claude-fable-5-1[1m]` 实际为 `claude-fable-5-1` | auto | timeout（题库任务未完成） | 2 | 2 | 2 |
| `eda612507b7c` | 22 | `claude-fable-5-1[1m]` 实际为 `claude-fable-5-1` | plan | stopped（采够后收口） | 5 | 5 | 5 |
| `b8c3265b7346` | 22 | `claude-fable-5-1[1m]` 实际为 `claude-fable-5-1` | manual | stopped（采够后收口） | 4 | 4 | 4 |
| `d1bfc8553044` | 22 | `claude-fable-5-1[1m]` 实际为 `claude-fable-5-1` | acceptEdits | timeout（题库任务未完成） | 2 | 2 | 2 |
| `cdc46228c7fb` | 22 | `claude-fable-5-1[1m]` 实际为 `claude-fable-5-1` | dontAsk | stopped（采够后收口） | 4 | 4 | 4 |
| `a5e1c7e68422` | 15 | `claude-haiku-5-5` | bypassPermissions | stopped（采够后收口） | 5 | 5 | 5 |
| `8ce0ebac7798` | 15 | `claude-haiku-5-5` | auto | stopped（采够后收口） | 4 | 4 | 4 |
| `50e6efe86bc5` | 15 | `claude-haiku-5-5` | plan | stopped（采够后收口） | 6 | 6 | 6 |
| `11f69f9adf2e` | 15 | `claude-haiku-5-5` | manual | stopped（采够后收口） | 6 | 6 | 6 |
| `953227502b65` | 15 | `claude-haiku-5-5` | acceptEdits | stopped（采够后收口） | 7 | 7 | 7 |
| `300a80ec66e9` | 15 | `claude-haiku-5-5` | dontAsk | stopped（采够后收口） | 7 | 7 | 7 |
| `87c53ff51767` | 22 | `opus[1m]` | bypassPermissions | stopped（协议样本有效） | 4 | 4 | 4 |
| `6bd3ddd367cf` | 22 | `opus[1m]` | manual | timeout（协议样本有效） | 2 | 2 | 2 |
| `b774937dc1cd` | 22 | `opus[1m]` | acceptEdits | stopped（协议样本有效） | 5 | 5 | 5 |
| `dbd2a897bafe` | 22 | `opus[1m]` | dontAsk | stopped（协议样本有效） | 4 | 4 | 4 |

完成集合均确认持久化 prompt 与系统既有 canonical 文本一致；实际 `/v1/messages` host 为 `api.anthropic.com`，UA 为 `claude-cli/2.1.293 (external, cli)`。最初三轮开始时间差约为 383 秒、199 秒；后续轮次由控制器按至少 120 秒、终态及容器清理检查后启动，精确时间保留在远端回执。

Sonnet 基线和 Auto 各包含三条成功主响应与一条标题响应，两轮采够后通过 stop API 收口，exit_code=143、容器已清理。Plan 的题库任务 timeout、exit_code=124，已收录两条完整主响应（含线程续轮与 safeguard SSE）及一条标题响应，CCH/后缀均命中。随后完成 Sonnet 其余三种权限模式，累计九轮、40 条 billing 验证通过；停止或超时状态不能当成题库任务完成。

## Fable 追加队列

- 用户明确要求追加 Fable 5.1。采用已实测 bootstrap 选项 `claude-fable-5-1[1m]`，不根据后缀预填 context beta 或 fallback 参数。
- 控制器已安全交接到 `capture-controller-v3.py`，PID 1139900，保留完成集合、冷却记录和原两小时截止时间。交接时没有正在运行的本轮抓包，未重启或重复任何 run。
- `fable-queue-update.json` 记录队列变更；Fable 基线/Auto/Plan 排在下一组，账号 ID 为 22。入队时账号 22 的既有养号 `06455cab8b0d` 仍在运行，控制器等待 account-busy 消除后才开始抓包。
- Fable 与 Opus 对应模式逐字段比较 beta、顶层顺序、max_tokens、thinking、output_config、字段类型、thread 和 safeguard SSE。实际差异触发同账号的三种额外模式，扩展结果单独记录，不预先假定全部相同。
- 账号 22 的既有养号随后 success，结束于 1791437278.769995，未见重试；Fable 新基线于 1791437297.7835357 开始，run ID 为 `8b9029853425`，主请求四条成功响应及一条标题 billing 全部命中，终态 stopped、容器已清理、提示词比对通过。
- 实际 wire 模型为 `claude-fable-5-1`；max_tokens=64000、adaptive/display updates、effort xhigh；beta 含 inline-tools 和 message-threads，未见 context-1m；本轮请求未出现 fallbacks。CLI `[1m]` 后缀不能替代对实际字段的判断。
- 与 Opus 基线不同的字段为 beta、max_tokens，`fable-mode-expansion.json` 已登记扩展 manual、acceptEdits、dontAsk。
- Fable Auto `5e7d7cf30b69` 收录一条成功主响应和一条标题响应，两条 billing 均复算通过；终态 timeout、exit_code=124，容器已清理。主请求为 64000 token、adaptive/display updates、xhigh，新增 dangerous-tool-use 和 afk-mode beta，带 safeguards 数组。SSE 的 status.tool_uses 是对象，一条工具关联与同响应中的 tool_use block 完全匹配；报告为 `5e7d7cf30b69-safeguard-associations.json`，不输出原始工具 ID。
- Fable Plan `eda612507b7c` 于 1791437930.058896 启动，1791438092.5208395 收口为 stopped、exit_code=143，容器已清理；四条成功主响应及一条标题 billing 均复算通过。主请求同样为 64000 token，带 Plan safeguards 和 SSE safeguard_results，线程续轮带 previous_message_id，未出现 context-1m 或 fallbacks。
- Fable manual `b8c3265b7346` 已收口为 stopped、exit_code=143，三条成功主响应及一条标题 billing 复算通过。acceptEdits `d1bfc8553044` 为 timeout、exit_code=124，收录一条成功主响应与一条标题；dontAsk `cdc46228c7fb` 为 stopped、exit_code=143，收录三条成功主响应与一条标题。六模式均完成容器清理与逐条复算，本组 22 条 billing 全部通过。
- Fable bootstrap 实际 cwk_cfg_key 为 sorrel、cedar_basin 为 2027-08-31；脱敏结构见 `8b9029853425-bootstrap-structure.json`。
- 已保存 `safeguard-tool-associations.json`：Opus/Sonnet 的 Auto/Plan 中，status 为对象，tool_uses 为对象；所有非空关联 ID 均出现在同一响应的 tool_use block 中，部分 Plan 结果合法地为空，不补造关联或分类结论。

## Haiku 5.5 主请求

- 账号 15 新基线 `a5e1c7e68422` 于 1791438972.0575962 启动，1791439134.134901 收口；HTTP 200 主响应四条和标题响应一条，五条 billing 的 CCH/后缀均通过。
- 主请求 max_tokens=128000、thinking 为 adaptive/display updates、output_config.effort=xhigh；没有 context-1m 或 fallbacks，thread 初始与续轮均已观察。标题虽然同为 128000 token，但没有 thinking 且含 title schema，不能混用画像。
- 主请求 beta 从 oauth 开始，claude-code-20250219 排在 mid-conversation-system-2026-04-07 后、per-turn-control-2026-07-01 前；其它完整顺序见 `a5e1c7e68422-protocol-shapes.json`。
- `/api/claude_cli/bootstrap` 的 query model 为 claude-haiku-5-5，HTTP 200，cwk_cfg_key=lovage、client_data.cedar_basin=2027-08-31；证据为 `a5e1c7e68422-bootstrap-structure.json`。
- Auto `8ce0ebac7798` 于 1791439156.7508256 启动，剩余权限模式仍在队列；当前已完成十六轮、67 条 billing。
- Auto 已终态 stopped，四条 billing 全部命中，七个非空工具关联均匹配。Plan `50e6efe86bc5` 已终态 stopped，六条 billing 的 CCH 均命中；原复算器按模型缓存后缀，误报其中两条续轮。实际响应链为请求 22→24→25 与 23→26，两链根后缀独立且各自稳定；请求 20 为单独标题。
- 已按 previous_message_id→SSE message_start.message.id 修正复算器，保留所有 `*-verification-v1.json`；`thread-lineage-verifier-recheck.json` 证明十八轮、77 条 billing 全部 CCH/后缀通过。脱敏关系图为 `50e6efe86bc5-thread-lineage-structure.json`，不包含原始会话或响应 ID。此误报只暂停本批队列，没有重启 capture、切号或增加提示词；恢复前仍复查账号和清理状态。
- 复核后从原队列交接到 `capture-controller-v4.py`，PID 1179957；保留原始截止时间 1791441172.7592175，不重启已结束 Plan。随后 Manual `11f69f9adf2e` 完成并复算六条 billing，累计十九轮、83 条全部通过。
- 账号 15 的既有养号 `8af40491e785` 于 1791439860.8590155 启动。控制器当前等待 account-busy，剩余 Haiku acceptEdits/dontAsk 和账号 22 的新 Opus 基线组；不停止养号或提前切号。
- 用户要求继续后，为剩余六轮增加一次最多 60 分钟的有界续采；矩阵仍为 25 轮，不重复已有样本。当前控制器为 `capture-controller-v5.py`、PID 1189766，权限守护为 `capture-permission-guard-v3.py`、PID 1189777；最终截止为 1791444772.7592175，守护清理余量截止为 1791445072.7592175。`bounded-continuation-window.json` 保留原截止和队列交接回执，到达新上限不自动再延长。

## 当前冷却

切换到账号 15 前，观察到其既有养号 run `5744cd6eec3c` 仍在运行，终端出现重试。检查未见 429、连续 5xx 或被动 quota 门禁，不将重试臆断为限流。依据抓包规范，对本轮矩阵留出至少 900 秒冷却；暂停的只有本轮采集控制器，不中断现有养号。远端 `cooldown-hold.json` 记录最早复查时间；恢复前重新检查账号、原任务终态与容器清理状态，不切回另一个账号继续突发采集。

冷却从 Unix 时间 1791434475.1575804 开始，1791435375.6855888 完成复查并恢复，间隔超过 900 秒；原养号任务已 timeout，容器清理、账号空闲、凭据结构有效、额度未阻止。Sonnet 5.5 新基线 `9a10fc90dd5c` 随后在账号 15 启动，实际版本快照仍为 293，现已完成主请求与独立复算。

远端控制器已交接到 `capture-controller-v2.py`，PID 为 1112591。交接保持当时正在执行的 `e07bd35e26dd`、已完成集合、剩余队列和原两小时截止时间，未重启 run。新增目标账号养号任务的重试冷却复查；若目标模型仅有标题、探测等辅助响应，控制器会停止后续矩阵，不将其当作主模型成功。

本轮受限目录权限守护先为 `capture-permission-guard.py`、PID 1121991，随后安全交接到 `capture-permission-guard-v2.py`、PID 1184701。新守护同时收紧本批 flow 目录和工作区 `.bench*` 对话日志：目录 0700、文件 0600，保持原所有者；截止时间仍为原控制器窗口加 300 秒清理余量。不改其它任务目录或养号配置。

## 已确认的 293 差异

- `version/version_base=2.1.293`，抓包中的构建时间为 `2026-10-07T06:36:42Z`。
- 消息请求 `X-Stainless-Package-Version=0.128.0`，Node runtime 为 `v26.3.0`，timeout 为 600。
- session hello 的 UA 仍为 `Bun/1.4.3`。不从 patch 版本推断 Bun 升级。
- MCP 列表实测 HTTP 200、UA `claude-code/2.1.293`、beta `mcp-servers-2025-12-04`、协议 `2025-11-25`；实际 header 名称为 anthropic-mcp-client-capabilities、mcp-protocol-version，能力解码为 roots.listChanged=true、elicitation 空对象，与 280 当前能力值相同。脱敏证据为 `76f9af2285bc-mcp-structure.json`，不通过臆造的 x-mcp header 名称判定缺失。
- Opus 主请求与 Haiku 标题请求均出现 `inline-tools-2026-09-15`；完整 beta 顺序保存在远端脱敏结构报告中。
- 自动标题请求已改用 `claude-haiku-5-5`，观察到 `max_tokens=128000`、无 `thinking` 字段、包含 title JSON schema。
- Sonnet 5.5 主请求已确认 `max_tokens=128000`、adaptive thinking/display updates、effort xhigh、inline-tools 和 message-threads beta；Auto 使用对应 safeguards 数组并收到 SSE safeguard_results。本矩阵显式固定 xhigh，不能据此宣称验证了其它 effort 档位。
- bootstrap 已观察 Opus 5.5 的 cwk 为 saffron、Sonnet 5.5 为 cardamom、Fable 5.1 为 sorrel、Haiku 5.5 为 lovage，client_data.cedar_basin 为 2027-08-31；原始额外模型选项继续是 Fable 5.1[1m]。不同账号的其它 client_data key 存在差异，不能将其全部固化为版本常量。
- 293 仍自动使用 `claude-haiku-4-5-20251001` 做 `max_tokens=1` 的连通性探测。停止旧模型专项升级不等于删掉客户端自动探测的兼容。
- Auto、Plan 的 Opus 主请求均带 `safeguards` 数组，其中 `type=dangerous_tool_use`，`classifier_context.permission_mode` 对应 auto 或 plan；响应结果位于 `message_delta.delta.safeguard_results` 数组，已见 item keys 为 type、status。
- 当前已验证的全部 billing 请求继续命中 280 的字节规则：seed `0x4D659218E32A3268`、所有精确字符串 `model` 清空、顶层 `max_tokens` 删除、fallback 保留。初始后缀按现有 UTF-16 规则命中，线程续轮沿 previous_message_id 对应的 SSE 响应身份继承所属会话后缀，不能用同 run/model 分组代替响应链。
- 全量结构汇总发现首轮 Opus `76f9af2285bc` 有一条 `fallbacks="default"` 主请求，HTTP 200、max_tokens=128000、adaptive/display updates、xhigh；无 thread，但 beta 含 message-threads。在 effort 后、thinking-binding-controls 前按顺序增加 server-side-fallback-2026-07-01、fallback-credit-2026-06-01；该条 CCH 也已命中。脱敏证据为 `76f9af2285bc-fallback-structure.json`。这仅覆盖 default 分支，不代表已验证其它 fallback 形状或 safeguard/fallback 联合组合。
- `matrix-audit.json` 全量核对已完成十六轮：系统 canonical 文本、293 版本/身份、官方 host、镜像固定、billing 复算、容器清理、终态后启动和工具关联均通过；最小相邻启动间隔为 184.50871348381042 秒。所有非空 safeguard 工具关联均能对应同响应中的工具块，原始工具 ID 不输出。
- 上述结论按已完成集合逐请求核对；Haiku 和 Opus 的剩余权限模式完成前，不宣称完整 293 画像已验证。仓库 `protocol-contracts.json` 只保存脱敏字段结构，不包含正文或身份，后续收口时刷新。

## 代码研究发现

- `cc2api/src/service/version_profile.rs::ClaudeCodeProfileSelectionConfig::resolve` 目前只精确匹配 260、280，293 会回退到默认画像。
- `cc2api/src/service/rewriter.rs::is_cc_version_thread_followup` 当前仅识别 280；新增 293 时需基于抓包扩展而保持旧版行为。
- `is_structured_haiku_title_request` 当前使用 32000 token 和 disabled thinking 的旧形状；293 的新标题形状需明确识别，不能误套主请求画像。
- `allowed_claude_code_versions` 与默认回退 profile 目前有联动；新增 293 并设为默认时，需明确准入范围与回退选择的关系，正确保存目标允许/禁止规则，并保留用户其它显式自定义准入配置。

## 仍待采集与核对

- Opus 换账号的新基线及 manual/acceptEdits/dontAsk 四轮；继续核对 thinking/output_config、beta 顺序、safeguards 与 SSE。Haiku 六模式已齐备。
- 换账号后的当前基线、账号轮换及间隔记录。
- 按每条最终请求字节复算全部 CCH 与 cc_version，并核对每个 run 的清理状态。
- 目标模型的 bootstrap 字段及 293 新后台端点差异；未采到的行为保持明确边界。
