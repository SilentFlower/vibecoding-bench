# 父任务总验收规划证据索引

## 当前归属

规划核对基线64d72ce633d26734779579c96d1d586226313ad3。以下记录是子任务已交付证据的索引；父任务执行阶段另行核对覆盖、生成验收矩阵和验证清单。历史真实Google研究与当前产品入口的供应商验收分别表达。

| 子任务 | 实际状态 | 业务提交 | 任务记录提交 | 主要来源 |
| --- | --- | --- | --- | --- |
| agy-managed-credential-contract | completed/closed | d022f372 | a99bee29 | research/credential-contract.md、contract-evidence.md及native-*-summary.json |
| multi-platform-account-auth | completed/closed | f2d9c4c6 | 6f82ec62 | research/implementation-validation.md及权威账号合同 |
| agy-account-runtime | completed/closed | c61d635b | 37aa1399 | research/implementation-validation.md及原版本地TLS证据 |
| agy-system-prompt-homoglyph | completed/closed | 8348b09b | c0c9122e | research/current-contracts.md、固定字符资源及原版本地TLS证据 |
| multi-platform-request-records | completed/closed | 754b90ab | 64d72ce6 | research/current-contracts.md及最终修复、双库、跨层证据 |

本表中的task目录前缀均为.trellis/tasks/11-18-。五个task.json及Close由规划阶段逐项读取，提交历史在当前分支核对。

## AC映射候选

| 原AC | 工程证据来源 | 历史原生研究 | 当前产品供应商/部署后待验 |
| --- | --- | --- | --- |
| AC01 | 账号平台迁移、ASGI鉴权、真实HTTP/SQLite替身、账号UI及CC回归 | 原生PKCE链接/取消、独立HOME登录基线 | 当前统一入口真实Google登录、身份及持久登录态 |
| AC02 | 原生目录映射、AGY调用Claude的HTTP/SQLite记录、固定AGY内核与平台标记 | 历史目录含18档模型 | 当前账号真实目录及Claude/Gemini模型接受性 |
| AC03 | 唯一管理所有者、跨进程锁、AT-only、CAS、并发刷新及代次保护 | 唯一helper真实刷新、常驻缓存限制、RT缺省工作副本 | 当前产品真实受管刷新、到期前更新及真实RT轮换 |
| AC04 | 同根401有界恢复、旧回执、工具跨代、SSE首帧后门禁、取消/中断与对账 | 真实工具等待发布AT2仍由AT1缓存处理 | 真实并发认证失败、工具跨AT实际到期及SSE首包后真实换代 |
| AC05 | 固定原版+本地TLS/MCP的普通/SSE/工具及排空 | 真实Google文本、SSE、MCP结果及遥测/退出研究 | 当前产品入口到真实Google的完整集成闭环 |
| AC06 | 真实管理API/SQLite筛选计数、工具前驱、独立控制收口、采集权限与文件边界 | 私有归属研究合同 | 生产数据与运行态验收沿发布流程 |
| AC07 | 账号/环境/请求页面真实构建浏览器探针，草稿焦点/迟到回执及390px | 不适用 | 发布环境实际页面检查 |
| AC08 | 固定26字符资源、账号冻结、恢复策略、实际Cortex/TLS系统段及历史保护 | 原研究同形字参考 | 真实分词、缓存与计费效果 |
| AC09 | SQLite/PG、冻结摘要、5→6重复迁移、旧程序compatible_newer读写 | 当前权威凭据恢复原则 | 生产备份、迁移、回退及真实账号身份保持 |
| AC10 | 本轮交付验收矩阵、证据清单、外部验收清单及父任务Close | 按原来源引用 | 所有外部待验项继续具名保留 |

## 最终批次证据候选

下列文件均位于gitignored运行目录.trellis/.runtime/，当前规划已核对存在及必要结果。执行阶段记录摘要、命令和覆盖关系，按变化范围判断复用。

- agy-records-rust-final.log：常规Rust整套970项通过，13项忽略；日志专项另行执行，禁止把忽略计为通过。
- agy-records-stream-log.log：独立日志用例通过。
- agy-records-repair-diagnostics.log：最后20项诊断回归通过，含工具完成后控制失败、取消先于回执、重复回执及原HTTP时间保持。
- agy-records-repair-http.log：20次真实HTTP/SQLite合成发送器提交通过，含401同根两尝试及AGY调用Claude。
- agy-records-repair-native.log：固定原版17次本地TLS合成生成通过，19条HTTP根记录、18次尝试，真实外部模型提交0。
- agy-records-native-off.log：采集关闭的固定原版场景通过。
- agy-records-full-chain.log及agy-records-full-chain/report.json：9类UI/API/SQLite场景通过，含旧程序读写及390px弹窗边界。
- agy-records-pg.log：独立PG诊断合同显式执行通过，临时容器和测试卷已回收。
- agy-records-management-ui.log：两主题和时区的既有管理页回归通过。
- agy-records-web-build.log：最终Vue构建通过。
- agy-records-python-core.log、agy-records-capture-api.log：相关49项及后续24项定向批次通过，重叠范围按批次表达。
- agy-records-deploy-all.log：部署223项通过。
- agy-records-python-all.log：1386项中1380通过、5跳过、1项既有python-dateutil项目种子摘要错误。
- agy-runtime-baseline-project-content.json：同一HEAD项目内容的期望/实际摘要差异，与任务相关验证分别登记。

## 交接限制

既有凭据研究原预算8次属于历史实验。本轮真实外部模型调用预算为0，使用当前私有原件、真实账号和生产环境均进入后续独立授权。工程结果、研究支持/限制和当前产品供应商待验状态分别保留，不将原生本地TLS合成用量解释为真实缓存或计费收益。
