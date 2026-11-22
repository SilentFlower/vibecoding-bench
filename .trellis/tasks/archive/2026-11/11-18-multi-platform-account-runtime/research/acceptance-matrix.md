# 多平台改造父任务工程总验收矩阵

## 口径与基线

- 当前源码基线：64d72ce633d26734779579c96d1d586226313ad3。
- 本轮范围：父任务R08/AC10的工程交付核对、证据汇总及后续验收交接。五个子任务均completed/closed，提交与状态身份见validation-evidence.json的children。
- E01—E23对应validation-evidence.json中的真实验证批次、退出状态、日志摘要及覆盖。重叠批次不累加，ignored不计通过。
- 历史真实Google研究以凭据合同及六份native JSON为来源。固定原版本地TLS采用合成身份和上游，仅表示原生工程链路。当前产品入口的真实供应商验收见external-acceptance.md，分别保持待验。
- 本轮真实外部模型调用预算0。父任务工程Close按已评审Brief定义执行，原AC的真实供应商要求继续保留。

## AC01—AC10对账

| AC及需求 | 实际实现、归属及源码合同 | 工程验证与结论 | 历史原生研究 | 当前产品外部待验 |
| --- | --- | --- | --- | --- |
| AC01 / R01、R02、R06 | account-auth；Account.platform、OAuthFlowService、agy_auth.AgyAuthManager及AccountStore；既有账号UI复用原授权与保存 | E01、E14、E15、E16、E21；平台隔离、并发唯一刷新、丢回执/重启/错身份、原账号重授权及CC账号回归通过 | 原生PKCE链接生成与取消、独立HOME登录基线 | EXT01真实产品授权/身份/持久登录态，EXT06套餐与额度语义 |
| AC02 / R01、R04 | account-auth→runtime→request-records；AccountService::agy_model取model_mappings，AgySubmission携带公开/原生模型及AT-only快照，Gemini按平台选择固定AGY内核 | E01、E05、E06；AGY调用Claude的真实HTTP/SQLite替身、平台/协议/实际提交映射及原版内核通过 | 历史原生目录包含18档模型，目录RT缺省/空串的支持与限制见凭据合同 | EXT02当前真实目录与Claude/Gemini接受性，EXT06能力口径 |
| AC03 / R02 | credential-contract→account-auth→runtime；管理层唯一RT所有者、按账号锁和pending/reconcile、complete_agy_commit的原身份/操作/代次CAS，业务只取得AgyAccessSnapshot | E01、E14、E18、E19、E21；并发刷新一次、回执未知恢复、原权威材料保持、共享封存映像及两代AT准备通过 | 常驻TokenSource保留旧AT；唯一helper真实刷新时AT改变，RT此次保持；真实RT轮换仅有合成保护证据 | EXT03当前产品受管刷新/真实RT轮换/到期前更新 |
| AC04 / R03、R05 | account-auth→runtime→request-records；gemini::drive有界oauth_recovery，ToolTurn保留原worker/attempt/调用方与截止，HTTP根/模型尝试/工具/物理控制分别记录 | E01—E06、E14、E21；同根两尝试、不同凭据代次、首帧后禁重放、容量零恢复、工具原许可接续、取消、中断与旧回执隔离通过；E03验证工具完成后控制仍未知、实际失败及重复回执 | 真实MCP等待期间发布AT2，原轮仍由AT1缓存处理，真实结果回填一次 | EXT04真实并发401、工具跨AT实际到期及SSE首包后换代 |
| AC05 / R04 | runtime；公共Gemini→账号发送器→监督器→固定原版→Google固定目标，源Gemini观察与实际MCP控制，平台运行排空门禁 | E05、E06、E18、E19；替身明确分层；固定原版本地TLS的普通/SSE、MCP两代续轮、重复拒绝、截断/容量、取消及物理释放通过 | 历史真实Google文本、Scanner/SSE、MCP结果、遥测采样及退出研究通过；并非当前产品集成结论 | EXT02真实产品Google闭环，EXT04实际到期/取消 |
| AC06 / R05 | request-records；RequestDiagnostic/AttemptDiagnostic.context、SQL筛选/计数、工具前驱、策略及有界私有阶段；admin管理查询与平台绑定读取 | E01、E03—E09、E11、E12；真实UI/API/SQLite、PG、源用量、关联归属、管理员/服务鉴权、代次、链接/硬链接、共享容量和过期保护通过 | 原生conversation/trajectory/toolCall归属研究只按必要摘要引用 | EXT07发布环境实际记录与权限核对 |
| AC07 / R06 | account-auth、runtime、homoglyph、request-records；Accounts/RuntimeEnvironments/RequestDiagnostics及既有ChoiceSelect、Dialog、分页与异步代次 | E09、E10、E15—E17；账号、环境、请求页草稿焦点、迟到反馈、平台组合查询、两主题/时区及390px边界通过 | 不适用 | EXT07发布环境页面与实际账号状态核对 |
| AC08 / R07 | homoglyph→request-records；按账号默认关闭的开关、单一26字符资源、transform_system、同HTTP策略冻结及actual回执，独立Cortex系统段 | E01、E05—E07、E11、E15；两账号隔离、恢复冻结、下一HTTP取新配置、普通/SSE一致、幂等、系统/用户/历史保护、实际提交及关闭采集通过 | 新-api固定映射作为研究来源，使用已纳入本仓的唯一资源 | EXT05真实分词、缓存与计费 |
| AC09 / R01—R07 | account-auth、runtime、request-records；gateway追加5/6、bench追加2，冻结摘要、稳定Any绑定、当前权威凭据和身份保留 | E01、E04、E08、E13、E20、E23；SQLite/PG、5→6/重复迁移、旧程序compatible_newer读写及数据定义bench2/gateway6通过 | 权威凭据按当前状态恢复的研究原则 | EXT07生产备份、迁移/回退及真实身份保持 |
| AC10 / R08 | 当前父任务；本矩阵、validation-evidence.json、external-acceptance.md及原AC映射 | 原AC与需求ID保留，五子项Close及已提交源码核对完成；本轮补验数据定义和管理驱动，父任务工程Check-All通过；Spec及精确Push/Close由后续门禁执行 | 历史来源有独立身份及覆盖标注 | 全部EXT项保留，最终状态不冒充真实产品供应商验收 |

## 关键跨子项接线

| 交接 | 实际字段/调用及保护 | 核验来源 |
| --- | --- | --- |
| 账号→凭据所有者 | Account平台与权威AT/RT；按账号锁、operation_id、generation、ready/pending/reconcile及CAS提交；同次能力与代理保存 | gateway/service/agy_account.rs、store/agy_credentials.rs；orchestrator/agy_auth.py；E01/E14/E21 |
| 凭据→环境/业务 | AgyAccessSnapshot仅account_id/credential_generation/access_token/expires_at/email，缺失RT；platform_api_environments独立关联AGY账号和环境 | gateway/service/agy_contract.rs；orchestrator/agy_environment.py；E05/E06/E18/E19 |
| 模型→执行身份 | 受信model_mappings决定native_model；平台保持AGY，固定1.5.9与源码SHA核验；账号共享只读映像并限制物理worker数 | gateway/service/agy_account.rs、agy_runtime.rs；agy_runtime/supervisor.py；E05/E06/E18/E19 |
| 工具→新HTTP/新代 | 原请求/attempt、调用方、历史和函数身份核对；先原MCP收口再读ready新快照，维持并发1及截止 | gateway/service/gemini.rs；agy_runtime/supervisor.py、kernel.py；E03/E05/E06 |
| 工具结果→物理收口 | tool_turn_finalized只更新工具；仅job_finalized登记control_state/control_observed_at；提前原生失败保留控制未知，原HTTP时间和结果保持 | gateway/service/diagnostics/agy.rs、gemini.rs；E03/E06 |
| 策略→提交/诊断 | enabled/rule_version在HTTP冻结，恢复复用；只转换独立system，rule_sha256/source/changed/计数与本attempt对应 | agy_runtime/system_prompt.py；gateway/service/agy_contract.rs、diagnostics/agy.rs；E05—E07 |
| 采集→管理页面 | 原HTTP、decoded_gemini与Cortex各标source；debug和账号开关共同门控，唯一平台环境/UUID/文件归属、no-store及共享预算 | gateway/service/runtime_bridge.rs；orchestrator/main.py、agy_runtime/capture.py；E08/E09/E11/E12 |
| 迁移→旧程序 | gateway版本6的nullable筛选投影与纯定义摘要；原1—5冻结；旧程序按compatible_newer实际读写 | gateway/store/request_records_schema.rs、database_migrations.rs；system_release.py；E04/E08/E20 |

上述源码简写的gateway根为services/gateway/src，orchestrator根为services/orchestrator。34个关键源码身份及当前提交一致性保存在validation-evidence.json。

## 已知基线问题

E22保留原编排全量1386项的1380通过、5跳过和1项python-dateutil种子摘要错误。本轮单独复测该用例仍得到相同错误，并在当前HEAD的隔离git archive中得到与工作树一致的实际摘要6841c1333e2b107b8a79096002fb10ef5ec3bb7e18ac1c58150d406f646e5d90，期望值为217058e8e1fe1dc0d86478ce10c39e3b2b7df50ee44ac90303f12c1f148b85ec。

该错误属于已有项目内容基线，保留原退出状态；本轮工程总验收记录其边界。当前产品代码与原AC的真实供应商结果分别表达。

## 工程交付结论边界

工程证据覆盖账号/凭据/环境/模型执行/策略/请求记录及CC兼容，最后修复有独立定向证据。原始真实供应商要求继续由EXT01—EXT07承接。任务完成态依本轮已评审工程收尾口径在最终推送成功后写入；本轮父任务工程Check-All通过；最终Close由交付流程在推送成功后同步。
