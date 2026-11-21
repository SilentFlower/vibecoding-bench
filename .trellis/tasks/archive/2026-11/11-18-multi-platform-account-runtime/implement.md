# 父任务工程总验收实施计划

## 已完成依赖

- [x] 首期范围为账号、受管凭据、运行环境、Gemini API、按账号同形体及请求记录，沿既有UI。
- [x] 凭据研究、平台账号授权、AGY运行环境、同形体和请求记录五子项均completed/closed。
- [x] 当前实现与子任务记录已交付到feat/agy-account-runtime，基线64d72ce633d26734779579c96d1d586226313ad3。
- [x] 父任务总验收Brief完成到期领取并激活，implement route=inline。

## 执行顺序

1. 核对五子项完成态、Close、实际业务和任务记录提交，保留原树及需求ID。
2. 生成research/acceptance-matrix.md，逐项覆盖AC01—AC09及本轮AC10，核对账号→凭据→环境→Gemini→工具→策略→请求记录的交接与CC兼容。
3. 生成research/validation-evidence.json，记录有效证据的来源、命令、退出状态、范围、文件身份及复用理由。结合当前源码/实际类型核对失效范围，按需补必要验证。
4. 生成research/external-acceptance.md，明确真实Google、实际到期、缓存/费用和生产迁移的待验项及独立授权边界；记录python-dateutil既有基线错误。
5. 进入父任务Check-All，收集并统一处置问题；通过后进行Spec评估和精确Push计划。
6. 按确认范围推送父任务产物与任务记录，并以工程口径完成父任务Close。

## 场景与期望

| 场景 | 核对路径 | 期望 |
| --- | --- | --- |
| 任务及交付归属 | 五子项task.json→Git记录→当前HEAD | 均completed/closed，提交和实际文件一致 |
| 平台账号与授权 | Account/管理API→唯一刷新所有者→权威存储 | CC兼容，身份/代理/能力/凭据同代提交，真实身份状态准确 |
| 请求、工具与代次 | Gemini→sender→原版/MCP→诊断DB | 同根恢复、原工具归属、独立收口和原HTTP结果正确 |
| 系统策略与采集 | 账号开关→冻结策略→实际Cortex→受控管理读取 | 来源准确，账号隔离，默认关闭，敏感与容量边界明确 |
| UI组合交互 | 账号/环境/请求页→API→实际持久查询 | 保持原控件、草稿焦点、异步隔离与390px边界 |
| 持久兼容与回退 | 冻结摘要→SQLite/PG→旧程序读写 | 现有身份及权威凭据保留，追加迁移一致 |
| 证据及外部待验 | 原日志/JSON→矩阵→外部清单 | 工程、历史原生及当前产品供应商验收分别标记 |

## 验证策略

优先复用已执行且覆盖当前范围的完整回归与最后定向修复证据。实际命令、退出状态及覆盖关系由执行阶段证据清单核对；以下命令是缺口需要时的已有入口，规划阶段不视为已执行。

```bash
python3 deploy/flower2api/verify_database_definitions.py
cargo fmt --check --manifest-path services/gateway/Cargo.toml
cargo test --locked --manifest-path services/gateway/Cargo.toml
npm --prefix apps/web run build
PYTHONPATH=services/orchestrator:deploy/flower2api /root/project/vibecoding-bench/.venv/bin/python -m unittest discover -s deploy/flower2api
```

- 隔离PG专项、HTTP/SQLite替身、固定原版本地TLS/MCP、UI/API/SQLite及既有管理浏览器探针分别核对，禁止将ignored计为已运行。
- Rust已有整套970项、独立日志项和最后20项诊断修复证据按批次保留。真实HTTP20次、原版TLS17次、采集关闭1次、跨层9类场景及管理页两主题已有证据。
- Python全量1386项为1380通过、5跳过、1项既有种子摘要错误；原失败、HEAD一致摘要与相关定向回归分别记录。
- 当前真实外部模型提交预算0。验证使用合成身份、临时数据库和断网容器；测试数据恢复及资源回收按既有探针合同执行。

## 文件与责任

当前父任务目录：保留prd.md原需求及ID；更新design.md、implement.md、JSONL、brief.md和历史上下文；新增上述三份执行产物及规划证据索引。产品源码缺口先登记明确问题并按所处阶段处理。其他已关闭子项保持既有状态。

## 收尾与恢复

Check-All通过→Spec评估→精确Push计划→确认执行→任务进度与Close。每个待验供应商项目保留责任及后续前提。失败保留实际证据和当前权威状态，生产恢复与真实账号操作由后续授权流程承接。
