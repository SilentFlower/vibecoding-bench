# Claude Code 2.1.293 采集与画像升级设计

## 边界与事实来源

本任务包含既有线上抓包功能的运维使用，以及 cc2api 的版本画像扩展。抓包操作已由用户本轮请求授权；完整 Brief 已确认并启动任务，产品代码与回归已完成。原始 wire 事实只来自正式 capture API，分析结果见 `research/capture-progress.md` 与受限远端证据。

规划阶段已有 Opus 的基线/Auto/Plan，以及 Sonnet 5.5、Fable 5.1、Haiku 5.5 六模式，共二十一轮及 97 条 billing 请求，CCH、后缀均命中。当时剩余四轮 Opus 等待账号 22 的既有养号结束；这些技术事实作为实施前的证据检查点，不通过猜测补常量，也不在证据不足时宣称验证通过。

实施前最终核对已完成 25 轮、112 条 billing 全量独立复算，四模型六模式全部收口，串行及容器清理通过。原始证据 75 个目录、300 个文件权限全部符合要求，本轮控制器和守护进程已结束。前述二十一轮说明为规划阶段事实快照。

## 采集控制

- 使用 `POST /api/captures/run`，固定 293、worker/sidecar `ac0d59b`、topic 1、xhigh、系统 canonical 文本，`prompt=null`。
- 账号按模型组轮换；已完成账号 22 的 Opus 基线组、账号 15 的 Sonnet 组、账号 22 的 Fable 组和账号 15 的 Haiku 组，之后为账号 22 的新 Opus 基线组。每次换账号从新的 bypassPermissions 基线开始，不拆分同模型组的账号/出口。
- 整体串行，相邻启动至少 120 秒；前轮终态、worker/sidecar 清理、日志停止重试后才继续。
- 原计划 19 个短窗口；用户追加 Fable 后，先增加其基线/Auto/Plan 三轮，至少 22 个窗口。Fable 的 beta/body/SSE 与主模型存在差异时扩展到六模式，总数至多 25 个窗口；保留原两小时控制器截止时间，达到上限时记录未完成矩阵，不无界延长。采够主请求与续轮后通过 stop API 收口，不人工输入继续提示词。
- 用户要求继续后，账号 15 的既有养号阻塞剩余六轮，其 timeout_sec=1800。为完成已授权的原矩阵增加一次最多 60 分钟的续采窗口，最终截止为原截止加 3600 秒；保留初始开始时间、所有回执和冷却状态，不重启已有 run、不增加矩阵轮数。续采上限到达仍未完成时停止并报告剩余项，不自动再延长。
- 重试、429、连续 5xx 或 quota 门禁触发暂停至少 900 秒；恢复前重查账号状态。目标账号忙时等待，不中断其既有养号。
- 本轮控制器有初始两小时上限和上述一次有界续采，具备唯一进程归属核对、受限记录和停止标记；冷却观察进程同样有明确截止，避免重复启动与无限后台采集。
- 运维脚本交接均保留当前 run、完成集合、剩余队列与冷却状态，未重启任何 capture；先后补充目标账号既有任务重试的冷却复查、成功目标主响应检查和按响应身份校验交错会话。只有用户继续后的有界续采交接调整截止时间，其它交接沿用原截止。

## 请求版本选择

沿用 `ClaudeCodeProfileSelectionConfig::resolve` 的原始 UA 精确选择，新增 2.1.293，保留 2.1.260、2.1.280 的映射和可选画像。未匹配、非法或缺失 UA 使用配置默认，出厂默认改为 293。请求体版本不参与选择，准入检查仍先于画像选择；目标允许/禁止配置拒绝 260 请求，而不删除其底层画像能力。

继续沿用 `account_for_request_profile` 的请求级账号副本，只覆盖版本、基础版本、构建时间与 Node runtime。账号 ID、持久设备身份、凭据、优先级、并发、RPM 等沿用原账号。重试、换账号及热刷新期间不重新选择当前请求画像，现有版本化缓存键继续适用。

## 293 描述表与协议分支

在 `src/service/version_profile.rs` 中建立独立 293 描述，保留 260、280 的注册、协议常量、输出行为和页面选项。已证实的 293 identity 为 2.1.293、构建时间 `2026-10-07T06:36:42Z`、Stainless 0.128.0、Node v26.3.0；hello UA 仍为 Bun/1.4.3。默认 SDK 改动必须检查所有引用，让旧画像继续使用自己的软件身份，不因默认切换而隐式改为 0.128.0。

- 主模型仅加入经采集确认的 Opus 5.5、Sonnet 5.5、Haiku 5.5 精确 ID；不以 family 前缀把未采集的旧模型套成新画像。
- Fable 5.1 单独采集与比较，使用当前 bootstrap 已暴露的 `claude-fable-5-1[1m]` 作为 CLI 入口；wire 模型、context-1m、fallbacks、thinking、beta 与 bootstrap 映射以本次证据为准，不能直接继承 280 的 Fable 表或靠名称推断。
- Fable 六模式均实测 wire 模型为 `claude-fable-5-1`、max_tokens=64000、adaptive/display updates；未出现 context-1m 或 fallbacks，但包含 inline-tools 和 message-threads。本轮不据 `[1m]` 自动插入 context beta，也不据旧模型历史表补默认 fallbacks。Auto/Plan 主请求已确认增加 dangerous-tool-use、afk-mode beta 和 safeguards 数组；两种模式的 SSE 工具关联均已校验，Plan 已收录线程续轮。其它三种模式与 bypass 的普通 beta 一致。
- 普通、Auto/Plan safeguard、Haiku 探测、标题与主请求分开建立 beta 表，按实际顺序维护 `inline-tools-2026-09-15`、message threads 及其它 token。
- 每个模型的 `max_tokens`、thinking、output_config 只取实际样本。新 Haiku 标题已观察为 128000 token、thinking 缺省、title schema；需要调整版本化分类，避免落入主请求分支。
- Haiku 5.5 的主请求同样为 128000 token，但含 adaptive/display updates thinking 和 xhigh；其 beta 从 oauth 开始，claude-code 排在 mid-conversation-system 后。建立独立精确模型表，不将它与标题请求或其它主模型混用。
- 最终逐形状核对发现 Haiku 5.5 还存在省略 claude-code 的普通主请求、以及省略 extended-cache-ttl 的 Plan 主请求。原生客户端的这两个 token 按其已携带的 beta 决定，保持表内顺序，不依据模式名称或 thread 字段猜测开关；API 缺少客户端选择信息时使用已验证的完整基线。旧画像可选 token 合并行为保留。
- 旧 Haiku 4.5 的自动 `max_tokens=1` 探测仍需兼容，但不追加旧模型专项任务或新主模型画像。
- CCH 候选继续使用已命中的 280 字节规则与 seed；全部矩阵逐请求复算通过后登记 293。保留精确序列化字节，不通过 JSON 往返重排后计算。
- 首轮 Opus 已实测一条 `fallbacks="default"` 请求：在 effort 后、thinking-binding-controls 前依次加入 server-side-fallback-2026-07-01、fallback-credit-2026-06-01；该请求没有 thread，但 beta 仍包含 message-threads，fallback 保留参与 CCH 且复算命中。普通无 fallback 样本不能覆盖这个条件分支；同时带 safeguard 与 fallback 的组合尚未采到，不根据单独分支外推。
- 293 线程续轮按已观察事实复用入站会话后缀；初始请求按首条 user message 的最后一个 text block 和 UTF-16 规则复算。260、280 的既有规则保持独立。
- Haiku Plan 已观察同 run、同模型的两条独立会话交错执行。复算器必须用 thread.previous_message_id 关联前一 SSE message_start.message.id，再逐链校验后缀继承；不得使用 run/model 作为唯一会话键。网关仍保留每条入站 billing 的会话后缀，不新增全局后缀缓存。
- `safeguards` 及未知嵌套字段原样保留，SSE 的 safeguard_results 按字节透传，不本地生成 classifier 结论。
- 后台端点与 bootstrap 只根据本次观察扩展精确分支；Opus 的 cwk 为 saffron、Sonnet 5.5 为 cardamom、Fable 5.1 为 sorrel、Haiku 5.5 为 lovage。client_data.cedar_basin 为 2027-08-31。没有采到的端点不依据版本号自动归类，未涉及的 client_data 字段继续保留上游值。
- 21 轮端点交叉核对确认：remote eval、penguin、bootstrap、MCP 列表使用 `claude-code/2.1.293`，grove 使用 CLI UA；不能沿用 280 的 eval Bun、penguin/MCP Axios UA。MCP capability 与协议版本仍沿用已命中的 280 常量。Hello 的 Bun UA 与 remote eval 区分，遥测流程保持本轮范围外。

## 默认回退与准入范围

默认回退改为 293，保留客户端模式的 260/280 映射并新增 293。默认准入上限扩展到 293，范围下限与语法沿用既有规则；显式自定义准入、阻止列表和 UA 规则保留。保存默认版本不得把已允许的 293 无条件压回 280。

用户明确要求通过设置页达到仅允许 280、293 的实际效果，目标交付配置为：

| 设置 | 值 |
| --- | --- |
| 画像选择方式 | `client_version` |
| 默认画像 | `2.1.293` |
| 允许 Claude Code 版本 | `2.1.89-2.1.293` |
| 禁止 Claude Code 版本 | `2.1.89-2.1.279,2.1.281-2.1.292` |
| 其它允许 UA | 保留管理员现有值 |

`AccessPolicy::check_user_agent` 先检查禁止规则，再检查允许范围；上述范围中的 260、279 和 281–292 被禁止，280、293 放行，294 及更高版本不在允许范围。260 不会先回退默认画像再绕过禁止规则。非 Claude 客户端继续遵守独立 UA 白名单，不能把“两版本准入”解释为删除其它客户端能力。交付配置是本任务的具体目标，不在启动迁移中无条件覆盖所有管理员的自定义禁止列表。

版本画像回退发生在已有准入门禁通过之后，不借本轮变更放宽缺失、非法 UA 或管理员阻止规则。只有客户端模式且存储范围精确匹配旧出厂组合时，迁移为新的出厂范围；范围语法与下限沿用既有规则。

账号画像模式保留原有目标画像准入策略。settings 写入、选择模式/默认画像与准入 reload 需维持事务和原子快照；SQLite、PostgreSQL 同步处理。旧出厂默认组合升级为 293；显式自定义的画像及准入规则保留，包括有效 260 配置。不新增针对 260 的强制迁移或失效 key 修复。

用户主动保存默认画像继续沿用既有账号软件环境同步行为，仅覆盖 `version/version_base/build_time/node_version`，不覆盖设备身份、凭据、容量和未知环境字段；账号基础版本与入站请求画像继续分别展示。新账号读取生效默认画像，出厂使用 293。设置保存需正确落库用户提交的目标允许/禁止规则，禁止列表不得因画像切换丢失。所有迁移幂等，在同一事务内完成应同步的配置与账号字段。

## 管理页与配置

版本选项通过现有后端 profile options 增加 293，保留 260 等已有选项；前端 fallback 描述、初始值、重置按钮和版本文案同步默认 293。账号列表继续展示账号基础版本、当前画像选择方式和默认回退，不把共享账号标成某个最近请求的版本。设置页清晰展示画像匹配与允许/禁止版本之间的关系，说明当前目标规则使 280、293 可用，而不是把底层支持版本硬编码缩减为两个。

遥测 UI、开关、采集维度与发送流程不作为本轮升级范围；采集中的现有 metadata 仅用于核对 software identity。

## 验证与交付

采集证据只保留受限远端；仓库 fixture 使用合成、脱敏内容，保留实际观察的字段结构和顺序，不能提交 token、完整 prompt、响应正文或账号身份。新增回归覆盖 260/280/293 的精确 UA、软件身份、模型 beta、标题分类、CCH/后缀、准入与配置热刷新、共享账号身份和缓存隔离；目标访问配置另外验证 280、293 放行，260、279、281、292、294 拒绝，禁止规则优先且默认回退无法绕过门禁。

本矩阵显式固定 xhigh；其它 effort 档位以及未在样本触发的可选 fallback 组合不计入实测覆盖，不能用合成回归代替实际客户端证据。若后续矩阵出现这些字段，单独记录并按字节复算。

完整矩阵未收口、存在 CCH/后缀失败或目标模型只有辅助请求时，不宣称 293 全部适配就绪。实现后的正式 Check-All、规范更新和精确 Git 提交流程按既有 owner 执行；本轮不自动部署线上 cc2api。
