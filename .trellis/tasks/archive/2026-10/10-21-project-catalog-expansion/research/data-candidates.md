# 数据存储候选：TinyDB 首批内容包研究

研究日期：2026-10-21。本文仅供 planning 审查，不是正式 catalog、已实现验收器或模型运行结果。唯一持久写入为本文件；没有修改固定上游 checkout、旧研究、产品源码或线上数据。

## 结论与接入边界

首批选 **TinyDB**，按 **4 个场景、12 项独立业务任务**准备：understand 2、consult 3、diagnose 3、plan 2、modify 2。10 项不要求源码修改，2 项针对已经复现的真实缺陷；不把实现、测试、文档、重试拆开计数。sqlite-utils 留到后续波次。

TinyDB 核心纯 Python、无 PyPI 运行依赖，已有固定版本在旧正式账号镜像 Python 3.12、UID 1000、无网络、只读根、256 MiB 下完整 228 项基线。最适合先验证已有 `schema:2`、`python-native`、固定源码、离线依赖、独立验收和模拟流程的内容扩容，不需要新增执行协议或服务。当前正式内容仍只有原来三项目；本结论不代表 TinyDB 已经正式接入。

当前无已证实必须改框架的阻断。进入实现前仍须完成 TinyDB 依赖 wheel 与精确 SHA 冻结、候选路径导入校验、私有 native/rubric、两修改参考解及反例、源码/许可证清单，并在**当前实际账号镜像**运行。既有 228 项基线使用 `v3-ci-39482854683-1`，不是当前线上修复镜像；不能沿用旧结果冒称已验证新镜像。1536 MiB 账号总预算、串行调度和原生验收份额应继续按现有平台契约分配；旧 256 MiB 子进程实测足以说明成本低，但不是本轮全链路资源证明。

## 来源、固定版本和证据核对

| 项目 | TinyDB | sqlite-utils |
| --- | --- | --- |
| 官方仓库 | <https://github.com/msiemens/tinydb> | <https://github.com/simonw/sqlite-utils> |
| 固定完整 commit | `edff96aeb2616402e9489d46e90a592c05565621` | `9c66bafa52ae23d40499c74b0db3b635bcddb876` |
| 固定版本 | 4.9.0 | 4.2.1 |
| Python 元数据 | `>=3.10,<4` | `>=3.10` |
| 许可 | MIT，保留 Markus Siemens 版权及全文 | Apache-2.0，保留 LICENSE 与来源 |
| 本地 checkout | `.deploy/github-100-research/data-tools/tinydb/source/` | `.deploy/real-project-review-20261021/sqlite-utils/` |
| 本轮 Git 核验 | HEAD 与固定 commit 相同，`git status --short` 为空，origin 为官方仓库 | 同左 |
| 原始证据摘要 | `evidence-sha256.json` 30 条全部存在、匹配 | `evidence-sha256.json` 15 条全部存在、匹配 |

本轮实际请求了固定 commit 的官方 raw GitHub `LICENSE` 和 `pyproject.toml`，四份响应均与本地文件字节完全一致：

- [TinyDB LICENSE](https://raw.githubusercontent.com/msiemens/tinydb/edff96aeb2616402e9489d46e90a592c05565621/LICENSE)：1080 字节，SHA256 `b0e2a2d39271e3d96b717d7be8235ac413d74797bf7f742f0801cfaad6c8c912`。
- [TinyDB pyproject.toml](https://raw.githubusercontent.com/msiemens/tinydb/edff96aeb2616402e9489d46e90a592c05565621/pyproject.toml)：1819 字节，SHA256 `aaf19383ac2460e4d4575cd0d7f8c0fcbc512c5ba42b19cbcac0562341a1a9ef`。
- [sqlite-utils LICENSE](https://raw.githubusercontent.com/simonw/sqlite-utils/9c66bafa52ae23d40499c74b0db3b635bcddb876/LICENSE)：11357 字节，SHA256 `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4`。
- [sqlite-utils pyproject.toml](https://raw.githubusercontent.com/simonw/sqlite-utils/9c66bafa52ae23d40499c74b0db3b635bcddb876/pyproject.toml)：2234 字节，SHA256 `ec133707085153fae34f663ec8934ec95a731575a2b3b7577347ec2de0ac432c`。

这只核对固定版本来源，没有追踪或采用最新 upstream HEAD。浏览器读取 TinyDB 固定树页一次受限，但固定 LICENSE 网页及 raw 文件成功；来源结论基于实际 Git 对象、官方 origin 和上述精确字节响应。

已有原始记录均可追溯，本轮**没有重跑完整上游基线**：

- TinyDB：`.deploy/github-100-research/data-tools/tinydb/{baseline-result.json,baseline-output/baseline-tests.xml,baseline-output/log.txt,smoke.py,smoke-output/log.txt,requirements-frozen.txt}`。228 passed，0 failed/error/skipped；pytest 1.917 秒、峰值 RSS 40,500 KiB，容器整体 2.425 秒，256 MiB/PID 64、network none、无账号 HOME，无 OOM、容器已清理。
- TinyDB 固定研究依赖：pytest 9.1.1、pytest-cov 7.1.0、coverage 7.16.2、PyYAML 6.0.3 及其记录的间接依赖。核心不需要 PyYAML；`tests/test_storages.py:test_yaml` 使用它。`pytest.ini` 默认覆盖率参数，可沿用明确的 `-o addopts=`；是否保留 coverage 依赖应在正式回归 contract 固定，不能本轮自行裁掉后称同基线。
- sqlite-utils：`.deploy/real-project-review-20261021/{baseline-result.json,baseline-tests.xml,account-runtime-result.json,account-runtime-tests.log,reproductions-result.json}`。宿主完整集合 1497 passed、16 skipped，墙钟 25.01 秒、峰值子进程 291,700 KiB；旧正式账号镜像只执行 FTS/convert/register_function 相关集合，75 passed。不能称 1497 项全在 256 MiB 通过。

## 本轮微复现与真实 API 锚点

本轮只执行一个 Python 3.12.3 的微复现进程，从固定 TinyDB checkout 显式导入，临时 JSON 文件限于母任务 `research/.tinydb-micro-*` 并自动清理。有效运行共 7 个探针，0.0136 秒、峰值进程 RSS 15,232 KiB。首次尝试因 `research/` 尚不存在，在创建临时目录前退出，没有运行产品逻辑；建目录后有效运行全部按断言结束。该宿主结果不等于账号容器资源验收。

| 探针 | 固定原版观察 | 证据状态 |
| --- | --- | --- |
| `update_multiple(iter([({'done': True}, Query().qty > 0)]))`，MemoryStorage | 两文档 `[True, False]`、返回 `[1]`，目标应为两文档均更新 | 本轮复现，旧 smoke 同样复现 |
| 同上，JSONStorage | `[True, False]`、返回 `[1]` | 本轮复现，旧 smoke 同样复现 |
| left/right 分别嵌套 `{'v':1}`/`{'v':2}` 的交叉文档，先左后右 fragment | 左 `[1]`、缓存右 `[1]`、直接右谓词 `[2]`；两个查询相等 | 本轮 MemoryStorage、JSONStorage 分别复现，旧 smoke 有相同因果证据 |
| JSONStorage 搜索结果嵌套 tags 被调用方追加 | 再次相同查询看到追加值；`clear_cache()` 后重新读取为原值 | 本轮确认，符合已写明的共享缓存文档约定 |
| CachingMiddleware(JSONStorage) 仅一次写入 | flush 前文件为空，显式 flush 后真实 JSON 正确，close/reopen 可读 | 本轮确认，正常缓冲行为 |
| 列表两条规则：先 increment，再按新 qty 打 stage | 返回 ID `[1,1,2,2]`，同一文档多规则按顺序生效 | 本轮确认，兼容语义应保留 |

已读真实定义及相关测试，以下是固定版本源码定位（相对 checkout）：

- [database.py](https://github.com/msiemens/tinydb/blob/edff96aeb2616402e9489d46e90a592c05565621/tinydb/database.py)：`TinyDB` 第 17 行、构造第 87 行、`table` 第 111 行、`tables` 第 135 行、`close` 第 214 行；未知属性委托默认 `_default` 表，storage 接口读写整库。
- [table.py](https://github.com/msiemens/tinydb/blob/edff96aeb2616402e9489d46e90a592c05565621/tinydb/table.py)：`Table` 第 35 行、构造第 94 行、`insert_multiple` 第 179 行、`search(cond)` 第 249 行、`update` 第 427 行、`update_multiple(updates: Iterable[tuple[...]])` 第 531 行、`upsert(document, cond=None)` 第 583 行、`clear_cache` 第 718 行、`_read_table` 第 779 行、`_update_table` 第 804 行。`search` 新列表中的文档对象与缓存共享，明确要求只读；`upsert` 更新全部匹配；`_update_table` 更新后清查询缓存。
- [queries.py](https://github.com/msiemens/tinydb/blob/edff96aeb2616402e9489d46e90a592c05565621/tinydb/queries.py)：`QueryInstance` 第 59 行，用 `_hash` 决定可缓存/相等；`_generate_test` 第 218 行解析字段路径；`fragment` 第 489 行 predicate 解析了路径，缓存键却只有 `('fragment', freeze(document))`；`map` 第 515 行明确令 `_hash=None`，带 callable 路径不得被强行改为可缓存。
- [storages.py](https://github.com/msiemens/tinydb/blob/edff96aeb2616402e9489d46e90a592c05565621/tinydb/storages.py)：`Storage.read/write/close` 第 48/60/71 行，`JSONStorage(path, create_dirs=False, encoding=None, access_mode='r+', **kwargs)` 第 84 行；write 在原文件 seek/write/flush/fsync/truncate，默认没有原子文件替换；`MemoryStorage` 第 164 行。
- [middlewares.py](https://github.com/msiemens/tinydb/blob/edff96aeb2616402e9489d46e90a592c05565621/tinydb/middlewares.py)：`CachingMiddleware` 第 76 行，`WRITE_CACHE_SIZE=1000`、write 第 108 行、flush 第 120 行、close 第 132 行；close 会 flush，但异常终止的持久化不是事务承诺。
- [operations.py](https://github.com/msiemens/tinydb/blob/edff96aeb2616402e9489d46e90a592c05565621/tinydb/operations.py)：真实公开 `add/subtract/set/increment/decrement/delete` 是原地文档回调；没有 `set_path`、`batch_changes`、`deep_fragment`、`copy_results` 等旧路线提案 API。
- [docs/intro.rst](https://github.com/msiemens/tinydb/blob/edff96aeb2616402e9489d46e90a592c05565621/docs/intro.rst)：明确不适合多进程/线程、索引、HTTP server、关系管理、ACID 或高性能需求。旧 intro 文字写的 Python 3.5+ 与当前 pyproject 不一致，接入要求以固定 pyproject 为准，不能照搬过时叙述。

## 验收和隔离共约

以下每项标明 `state`（当前已知事实/最终应观察状态）和 `hypothesis`（需进一步证伪的候选解释）。这是研究用语，**不是新增 schema 字段**。最终清单继续用现有 `kind/outcomes/requires/materials/allowed_paths/evaluation` 表达。

`oracle` 指控制端私有 `verification/`、reference、rubric 和冻结 native，用于独立判断。它们不能复制到 candidate 的 library/app/materials，不得进入 `allowed_paths`，模型不能读 reference 答案或参考补丁；项目公开上游 tests 只是上下文，修改它们不能影响控制端固定回归。native 必须证明 `tinydb.__file__` 属于本次冻结 candidate，不能意外导入离线依赖内已安装的旧 TinyDB。

纯文字 understand/consult/plan 使用私有源码事实与 rubric 语义判断。下述“原生正常/反例”对这些任务是**rubric 的事实探针或引用示例的独立执行设计**，本身不能判定文字回答正确；不可把探针 exit 0 当作回答通过。需要可执行答复的 C02 使用现有答复代码提取模式，不增加公开协议：在唯一完整 Python fenced code block 中给示例，native 放入临时脚本、导入当前 candidate 后真实执行，缺失或多个矛盾示例要拒绝或受阻，不能挑一个碰巧通过的片段。所有新增 native/ref 均处于设计态，尚未构建/执行。

非修改任务 `allowed_paths=[]`；临时试验文件不发布到候选。两 modify 独立场景中不互相 require，不强迫只有完成所有问答才可以修复；默认路线可保留业务上下文串行，另提供 diagnose-only/modify-direct 入口，在直接入口显式附足已核材料。TD-S02 与 TD-S03 使用独立工作区，各自从固定原版起点开始，修改后各自执行完整 228 项上游回归，不跨场景传递代码或承诺累计修复。每个场景内同缺陷诊断须早于对应修改，不能要求已修复工作区继续复现原版失败。

业务资源建议：沿用现有 business 256 MiB/30 秒原生验收、单任务候选 600 秒/累计 1800 秒；修改后完整冻结 228 项回归可先沿用现有 regression profile（是否最终可设 256 MiB/30 秒必须当前镜像实测），不新增账号份额或并发。问答 native 预计各不足数秒，完整基线旧实测不足 2 秒，这些只是已有证据推断，非新包全链路测量。2 modify 完整回归约 456 项是规划执行量，不是本轮测试结果。

## 场景 TD-S01：单机订单小工具接入

### TD-U01 · understand · 中文目标：理解订单从 API 到文件的路径和数据边界

- **业务问题**：接手单人订单小工具，想知道 TinyDB 负责什么、默认表与具名 orders 表是什么关系、关闭重开后数据在哪里。
- **state / hypothesis**：源码事实为文档型本地存储；TinyDB 负责 storage 和表句柄，不提供 HTTP 服务/关系模型；默认调用委托 `_default`，`table('orders')` 不等于默认表。无待归因 bug。
- **真实锚点**：`database.py:TinyDB.__init__/table/__getattr__`、`table.py:insert_multiple/_update_table`、`storages.py:JSONStorage`。
- **材料/披露**：初始只给单人、本机、小数据、需要关闭重开的需求说明和固定源码；无需披露。不能提供内部标准答案。
- **正常原生事实/语义**：临时 JSON 创建默认表与 orders 各一单，关闭重开，分别核表名/ID/内容；文字须解释数据库—表—文档和持久化路径。
- **反例**：只对 orders 插入时 `_default` 应空；MemoryStorage 新实例不保留数据；将默认/具名表说成同一张或承诺网络服务为错误。原生事实不能替代文字评分。
- **允许路径/依赖**：`[]`；无前置任务。建议结果 `understood`。
- **英文 prompt 简稿**：`I am taking over a small, single-user order notebook. Explain what this frozen TinyDB project does, how a call reaches the stored JSON file, and how the default table differs from table('orders'). What survives closing and reopening the database? Ground the explanation in the current code; do not change files.`
- **资源/风险**：事实探针轻量；有默认表/具名表与旧 intro Python 版本混淆风险。未构建本任务验收器。

### TD-C01 · consult · 中文目标：判断多进程服务是否适合沿用 TinyDB

- **业务问题**：团队准备把单人脚本接到 4 个写 worker，还要求跨表订单/库存 ACID，是否继续用当前 TinyDB。
- **state / hypothesis**：需求已明确超出官方适用边界，合理结论为不建议直接继续；无需改 TinyDB 核心，更不能声称加 CachingMiddleware 就有锁或事务。
- **真实锚点**：`docs/intro.rst:Why Not Use TinyDB`、`table.py:_update_table` 整库读—改—写、`storages.py:JSONStorage.write`。
- **材料/披露**：初始明确并发和原子性要求；无需披露。方案可建议 SQLite 等满足场景的替代，但本任务不迁移、不改线上数据库。
- **正常原生事实/语义**：两套 JSONStorage 在临时文件保存不同已读快照，再顺序写回，观察旧快照覆盖新值，作为缺失协调的确定性事实探针；文字要指出单实例边界、迁移/单写者方案和数据验证步骤。
- **反例**：同一实例串行小数据应工作；不能以“JSONStorage 有 fsync”推导事务/并发安全，也不能执行 nondeterministic 并发压力后把一次成功当保证。
- **允许路径/依赖**：`[]`；无。建议结果 `advice`，不是 modify。
- **英文 prompt 简稿**：`We plan to turn the notebook into a service with four writer processes and require an order and inventory change to commit atomically. Is the current TinyDB implementation an appropriate fit? Explain the relevant guarantees and recommend a practical next step. Do not implement a new database or modify files.`
- **资源/风险**：不跑并发服务；确定性临时文件事实探针，预计极低成本。是否给出合适建议仍需语义评分。

### TD-C02 · consult · 中文目标：用现有 API 给出可重开的最小订单接入示例

- **业务问题**：单用户先保存两笔订单，只递增 SKU A 的 qty，关闭重开再按 SKU 查询，要求示例可直接运行。
- **state / hypothesis**：全部由现有 `TinyDB`、`table`、`Query`、`operations.increment` 实现，无须新 API 或核心修改。
- **真实锚点**：`database.py:table/close/__enter__/__exit__`、`table.py:insert_multiple/update/get`、`operations.py:increment`；旧 smoke 和本轮规则探针支持 API 使用。
- **材料/披露**：给两单 JSON（A=1、B=2）、具名 orders、数据库路径由示例输入参数获得；无需披露。示例不依赖当前工作目录中的账号文件。
- **正常原生验收**：答复唯一完整 Python 代码块写入独立临时脚本，传临时 DB 路径，真实执行后重开核 A=2、B=2，orders 两项且默认表无业务记录；脚本重复运行应在独立空目录验证，不额外要求未请求的幂等导入。
- **反例**：qty 递增误写成 `set('qty', 1)`、误用 `_default`、漏 close 的缓冲假成功、硬编码只打印期望、虚构 `save/commit` API 均不能通过真实文件与查询核对。允许运行方式等价，不匹配字面代码。
- **允许路径/依赖**：`[]`；无。建议结果 `usable_example`。
- **英文 prompt 简稿**：`Give me one complete runnable Python example that accepts a JSON database path, stores orders A(qty=1) and B(qty=2) in table 'orders', increments only A using existing APIs, closes the database, and reopens it to query A. Include the invocation. Do not create project files or change TinyDB itself.`
- **资源/风险**：答复提取与实际候选路径证明复用现有方式；防止示例绕过业务 API 或只伪造输出。新例检查未测。

## 场景 TD-S02：查询结果不一致分诊

### TD-D01 · diagnose · 中文目标：先补材料，再辨别共享缓存文档的正常约定

- **业务问题**：只报告“搜出来的订单 tags 自己变了，是库 bug 吗”，缺调用代码、storage、修改方式。
- **state / hypothesis**：初始信息不足；可能调用方原地修改返回对象、写 API 更新、其他进程或损坏文件，不能一开始断言缓存缺陷。披露后固定为 JSONStorage 搜索返回文档嵌套列表被调用方 append，属于当前公开共享只读约定。
- **真实锚点**：`table.py:search` 第 249 行 docstring 与缓存浅列表拷贝；`tests/test_tinydb.py:test_query_cache_documents_are_shared_with_cache`；本轮 JSONStorage 清 cache 复读对照。
- **材料/披露**：初始只有症状；合格请求后披露最小 caller.py、JSONStorage 配置、连续两次相同 search 与 `tags.append`、close/reopen 原值结果。披露必须用真实材料全文，不把标准解释透露给候选。可保留 `insufficient_information` 为无材料入口的合理终点；正常入口继续披露至最终诊断。
- **正常原生事实/语义**：独立临时 JSON 证明第二次同查询能见缓存嵌套追加，但 clear_cache/reopen 后原值不变；候选须区分缓存对象与持久写入，建议只读/应用复制或用 update，且不改库。
- **反例**：列表 append 一条 fake doc 不应污染缓存列表；通过 `update` 修改应清缓存并真实持久化；把所有情况都归因为 fragment 缓存键或承诺原地改返回文档会落盘为错误。
- **允许路径/依赖**：`[]`；无。正常结果 `diagnosed_no_code_change`，初始无材料分支 `insufficient_information`。
- **英文 prompt 简稿**：`An order's tags seem to change after I search for it. Is this a TinyDB bug? Tell me what evidence you need before drawing a conclusion. Do not patch the library on the basis of this report alone.`
- **资源/风险**：至少两轮正常澄清，澄清不增加业务尝试。JSONStorage 和 MemoryStorage 引用行为不可混为一谈；本任务固定 JSONStorage。

### TD-D02 · diagnose · 中文目标：定位不同嵌套字段 fragment 查询的缓存串用

- **业务问题**：订单有 billing/shipping 两个嵌套区域，先按 billing.city 查再按 shipping.city 查却返回相同订单；单独运行 shipping 谓词是正确的。
- **state / hypothesis**：已复现真实库问题；待验证假设为字段路径没进入查询身份，而不是数据库有重复订单、JSON 解码或 predicate 本身错误。
- **真实锚点**：`queries.py:fragment/_generate_test`、`QueryInstance.__eq__/__hash__/is_cacheable`、`table.py:search`；本轮 Memory/JSON 双存储微复现。
- **材料/披露**：初始完整两订单 JSON、caller.py、两次查询 ID 与直接谓词对照；无需再披露。用业务字段 billing/shipping 时须实现前重新按等价最小数据实测，而不能仅更名描述后冒称已执行；已测原始 left/right/v 片段保留为私有证据。
- **正常原生事实/语义**：原版左后右缓存 ID `[1]/[1]`、直接右 `[2]`，反向顺序也验证；文字须连起 fragment identity→QueryInstance equality→Table cache 的因果，不要求产出补丁。
- **反例**：不同 fragment 值、清缓存后单独查询、cache_size=0 的旁路应不串；无缓存条件下仍错误不能套用本结论。不得把临时 `clear_cache` 说成根治。
- **允许路径/依赖**：`[]`；无。建议结果 `diagnosed`；D01 不作为硬依赖。
- **英文 prompt 简稿**：`Two orders have different billing and shipping objects. A billing fragment search followed by the same fragment on shipping returns the first search's IDs, while applying the shipping predicate directly gives different IDs. Use the attached reproducer and current source to explain the cause, distinguish it from a data problem, and suggest a safe temporary workaround. Do not change files yet.`
- **资源/风险**：少量内存/JSON 临时数据；根因已证实，业务化材料尚未冻结。

### TD-M01 · modify · 中文目标：让 fragment 缓存身份包含完整字段路径

- **业务问题**：修复 TD-D02，保留缓存收益和当前公开 API。
- **state / hypothesis**：当前已确认 `fragment` 缓存 identity 缺 `self._path`；验收目标是不同完整路径的等片段结果不互相污染。修复策略可不同，不硬编码参考实现。
- **真实锚点**：`queries.py:fragment` 第 489 行；`map` 第 515 行不可缓存；根级 fragment、嵌套 fragment 现有测试第 507/517 行。
- **材料/披露**：完整公开最小复现/目标/兼容边界；直接修改入口同样提供，不依赖诊断回答文字。不披露私有 reference patch。
- **正常独立原生验收**：两不同路径、相同 fragment 的两种顺序，Memory/JSON、重复命中，结果分别 ID1/ID2；根级/空片段、深路径、AND/OR、缺失字段、不可哈希参数降级、`map` 不缓存保留；比较实际返回值，不靠 hash 数值恰好不同。
- **反例**：原版明确失败；恒禁所有缓存、改 search 返回全部、只针对 billing/shipping 字符串特判、忽略 fragment 内容或改 `_generate_test` 使缺路径异常消失均应由对照拒绝；独立回归恢复固定上游 tests 后运行完整集合。
- **允许路径/依赖**：最小产品路径 `library/tinydb/queries.py`；公开回归可改 `library/tests/test_queries.py`、`library/tests/test_tables.py`。不允许 `verification/**`、环境依赖、构建配置、Table 存储逻辑。`requires=[]`，目标和复现已自足；默认路线 TD-D02 在前，modify-direct 入口只包含本任务且材料完整，符合现有 loader 的入口前置可达性限制。
- **英文 prompt 简稿**：`Fix the nested fragment query-cache collision demonstrated here. Queries with the same fragment on different complete field paths must return their own matching documents regardless of evaluation order. Preserve root-level fragments, missing-field behavior, normal query caching, and the uncacheable map-path contract. Add focused regression coverage without changing storage APIs or private verification files.`
- **资源/风险**：business + 完整原生回归；旧完整成本见前文。两修改之一，严格小范围；不可把可调用路径强制可哈希。参考解/新验收未实现。

## 场景 TD-S03：批量促销规则一致性

### TD-U02 · understand · 中文目标：解释多规则顺序和重复返回文档 ID

- **业务问题**：批量规则先递增 qty 再按新 qty 打 stage，返回 `[1,1,2,2]` 是否意味着四个订单或重复落盘。
- **state / hypothesis**：列表规则按文档外层/规则内层依次应用，后规则看得到同一文档前规则的修改；每次命中都追加 doc_id，返回重复 ID 是现状，非新增文档。不得把 ID 去重当“顺手修 bug”。
- **真实锚点**：`table.py:update_multiple` 第 531 行、`_update_table`；本轮列表双规则 ID 微探针；`tests/test_tinydb.py:test_update_multiple_operation`。
- **材料/披露**：初始两单、两条列表规则、返回 ID、qty/stage 结果；无需披露。与一次性 iterator 症状分离，不提前泄漏其根因。
- **正常原生事实/语义**：两单 qty0→1→stage ready，返回 `[1,1,2,2]`，真实订单总数仍2；文字解释返回是命中记录而非新插入计数。
- **反例**：反转规则顺序时 stage 不应错误提前命中；无匹配规则返回空，不能把去重 ID/顺序无关性作为原有承诺。
- **允许路径/依赖**：`[]`；无。建议结果 `understood`。
- **英文 prompt 简稿**：`Our two promotion rules first increment qty, then mark orders whose new qty is 1 as ready. update_multiple returns [1, 1, 2, 2] for two orders. Explain the rule evaluation order and what the returned IDs mean. Is it evidence of duplicate orders? Use the supplied list-based example and current source; do not change the implementation.`
- **资源/风险**：微数据，成本极低；只读理解任务，避免将正常重复ID变成第三个修改目标。

### TD-D03 · diagnose · 中文目标：定位一次性规则流只更新第一单的原因

- **业务问题**：从配置加载器拿 generator，列表时全部订单更新，直接传 generator 后只有第一单变化。
- **state / hypothesis**：已复现真实 iterable 兼容问题；原因假设为嵌套循环反复消费同一个一次性规则迭代器，应以数据和源码确认，不能误判 Query 条件漏匹配。
- **真实锚点**：`Table.update_multiple(updates: Iterable[...])`、外层 docs/内层 updates；Memory/JSON 双复现 `[True,False]`。
- **材料/披露**：初始提供同一 loader 产出、至少两订单、同一条件的 list/generator 对照；无需披露。给原版运行输出，不给补丁。
- **正常原生事实/语义**：生成器场景原版返回 `[1]` 且第二单未标记；列表对照两单都标记、ID `[1,2]`，谓词对第二单直接为真；文字定位规则耗尽，提出短期 caller 将有限规则 materialize 的办法。
- **反例**：规则本来只匹配第一单时列表也只改一单，应区分；零订单/空规则正常；不能将所有 generator API 泛称不支持。诊断不产生源码 checkpoint。
- **允许路径/依赖**：`[]`；无，U02 不硬依赖。建议结果 `diagnosed`。
- **英文 prompt 简稿**：`The same promotion rules update every order when passed as a list, but only the first order when passed as a generator. Diagnose this with the attached list/generator control and the current Iterable-annotated update_multiple implementation. Explain a minimal caller-side workaround. Do not modify the library yet.`
- **资源/风险**：微数据已证实；仅有限规则，不能建议对未知无限流无条件 list 而不解释边界。

### TD-M02 · modify · 中文目标：让有限一次性规则与列表规则更新结果一致

- **业务问题**：配置 loader 合法返回有限规则 generator，要求 `update_multiple` 对所有目标一致应用。
- **state / hypothesis**：真实缺陷已复现；目标为对本次有限规则集固定一次、保证所有文档看到同序规则，而非新增事务或批处理 API。
- **真实锚点**：`table.py:update_multiple` 第 531 行；列表现状必须保留 TD-U02 顺序和重复 ID；`_update_table` 对 storage 的现有引用/异常语义不在本次扩展。
- **材料/披露**：公开两单一规则最小失败以及两规则顺序对照；直接入口同样带材料。私有参考补丁与独立测试不给候选。
- **正常独立原生验收**：list/tuple/iter(list)/generator 在 Memory/JSON 的同数据同规则得到相同文档与返回 ID；多规则重复命中保持 `[1,1,2,2]`；空集/无匹配/单文档、callback 原地修改、后规则依赖前结果均覆盖。
- **反例**：规则迭代过程先产一条随后抛异常时，本次规则尚未完整可用，应在修改文档前抛出，不把半份规则提交；持久 JSON 文件前后相同，MemoryStorage 也不得因 alias 已局部修改。此处只保证规则枚举前失败，不扩大为任意更新回调异常下的新事务保证；原版失败、只 materialize 在文档循环内部/循环后、只更新首文档或丢掉重复ID均应拒绝。固定上游 tests 全量回归。
- **允许路径/依赖**：最小产品路径 `library/tinydb/table.py`；公开回归可改 `library/tests/test_tinydb.py`。不允许改变 storage/default API、全部 callback 异常策略、`verification/**` 或依赖。`requires=[]`，目标和复现已自足；默认路线 TD-D03 在前，modify-direct 入口只包含本任务且材料完整。
- **英文 prompt 简稿**：`Make update_multiple apply a finite one-shot iterable of update rules to all matching documents just as it applies an equivalent list or tuple. Preserve rule order, in-place callback behavior, repeated returned IDs, and existing storage interfaces. If enumerating the rules fails, no part of those rules should have been applied. Add focused regressions; do not introduce general transaction semantics or modify private verification files.`
- **资源/风险**：materialize 的内存与规则数成正比，场景明确有限小规则；不接受无限流兼容承诺。完整回归同前，参考解/验收未实现。

## 场景 TD-S04：落盘预期、导入和可靠性方案

### TD-C03 · consult · 中文目标：解释缓冲写入的落盘时点并给出现有配置建议

- **业务问题**：启用 CachingMiddleware 后 insert 已返回但旁边打开的 JSON 文件还是空，是否说明写丢失；单人脚本退出前怎样确保正常 flush。
- **state / hypothesis**：该材料固定为正常缓冲：不足1000次且未 flush/close；不应改库强制每次 write。正常 close/context manager 会 flush，但进程崩溃/断电窗口仍须说明。
- **真实锚点**：`middlewares.py:CachingMiddleware.WRITE_CACHE_SIZE/write/flush/close`、`database.py:close/__exit__`；本轮缓冲文件微探针。
- **材料/披露**：初始提供配置、1次insert、关闭前文件大小和调用顺序；无需披露，不隐藏 shutdown 事件来诱导猜测。
- **正常原生事实/语义**：独立原生临时文件证明 flush前为空、flush后/reopen有订单，正常 context退出同样落盘；文字建议显式flush/with或按需求选择不缓冲，并描述延迟持久化代价。
- **反例**：默认 JSONStorage 单次写不走同一缓冲；已正常close仍丢失不应套用相同结论；不以“close有flush”保证kill -9、故障文件系统或事务安全。无需主动杀进程。
- **允许路径/依赖**：`[]`；无。建议结果 `advice_no_code_change`。
- **英文 prompt 简稿**：`With CachingMiddleware(JSONStorage), insert returns successfully but the JSON file is still empty after one write. The script has not flushed or closed the database yet. Explain whether this matches the current implementation, how to ensure a normal script exit publishes the data using existing APIs, and what failure window remains. Do not change the library.`
- **资源/风险**：不执行真实崩溃/磁盘故障；现有正常路径本轮验证，异常持久化边界以源码事实和语义评审判断。

### TD-P01 · plan · 中文目标：规划有限本地订单导入，利用现有批量 API 控制写入次数

- **业务问题**：单写者、1000条有限订单，目前循环 insert 很慢；需保存数据、重复运行时按 SKU 更新，并希望先审核方案。
- **state / hypothesis**：`insert_multiple` 批量一次存储写可用于纯新记录，`upsert` 是单条 API且更新全部匹配；没有 `upsert_multiple`。业务要求包含重复SKU时，应先澄清/确定冲突规则再规划，不把逐条 upsert 宣称单次提交或事务。
- **真实锚点**：`table.py:insert_multiple/upsert/_update_table`、`middlewares.py:write/flush`、`docs/intro.rst` 单写者范围。
- **材料/披露**：初始附1000条输入的schema和已有 importer.py，但重复SKU策略未给；合格提问后披露“输入同SKU后者覆盖，库内若已有重复SKU则停止并输出冲突清单，保留原库”。这是方案需求，不在任务中实现 importer。
- **正常原生事实/语义**：控制端计数 Storage 子类可证 `insert_multiple` 与逐条 insert 的read/write差别，临时小数据证 upsert 更新全部匹配；文字应提出先校验/备份、检测冲突、定义重跑语义、分批或现有缓冲的取舍、最终flush/reopen验收，不虚构批量upsert API。
- **反例**：只用 insert_multiple 导致重跑重复、无限盲重试、用 CachingMiddleware 声称原子事务、为加速删除校验均拒绝。方案通过不是实际性能提升或已执行迁移。
- **允许路径/依赖**：`[]`；无。建议结果 `plan_ready`，初始可 `insufficient_information`。不 require C03，相关配置初始自带。
- **英文 prompt 简稿**：`We import a finite file of about 1,000 orders in one writer process. Repeated insert calls are slow, and rerunning the import must reconcile existing orders by SKU. Review the attached importer and propose a safe plan using APIs that actually exist in this version. Ask about unresolved duplicate-SKU rules before fixing them in the plan. Do not implement or run a migration.`
- **资源/风险**：不做1000条性能基准；小数据counting storage只核源码事实。写次数少不等于总复杂度低，TinyDB仍整库扫描/存储。

### TD-P02 · plan · 中文目标：制定本地 JSON 备份及崩溃恢复边界，不承诺现有原子写

- **业务问题**：离线订单本机使用，希望文件写中异常时可恢复；只要设计方案，不能把研究中的原子存储提案当成已有 API。
- **state / hypothesis**：默认JSONStorage有flush/fsync/truncate，但当前同一文件覆盖并非临时文件原子replace；没有核心事务、官方 `export_backup/import_backup` 或 `AtomicJSONStorage`。
- **真实锚点**：`storages.py:Storage/JSONStorage.write`、`database.py:storage/close`、官方存储扩展点；旧 TinyDB 20步中相关项明确是提案。
- **材料/披露**：初始明确本地单写者、允许停写备份、JSON格式、恢复时需保持具名表/doc_id；无需披露。可以优先提出停写close后备份/校验、离线恢复演练；若提出可选Storage扩展，标为后续设计而非立即实现。
- **正常原生事实/语义**：独立临时fixture核close后备份的多表/ID与恢复后下一ID；只用合成数据。文字应写清备份一致时点、校验/坏JSON拒绝、目标非空冲突、恢复演练和取舍；建议可选临时文件发布时描述序列化/替换前失败保原件与同目录要求，但不要求此任务交付新存储。
- **反例**：fsync 不等于所有写入原子；不能声称现有 `close` 自动备份、跨进程锁或强ACID；不允许拿有效空JSON覆盖坏库后假称恢复成功。停止在方案评审，无真实文件迁移。
- **允许路径/依赖**：`[]`；无。建议结果 `plan_ready`。
- **英文 prompt 简稿**：`For this single-writer local order notebook, propose a backup and recovery procedure that preserves tables and document IDs and makes the failure boundaries explicit. Explain what JSONStorage.write currently guarantees and what it does not. Prefer a reviewable operational plan; if you discuss an atomic-storage extension, label it as proposed work rather than an existing API. Do not implement it or touch real data.`
- **资源/风险**：只读设计/合成副作用事实核验；禁止扩成生产数据库迁移或复杂跨平台原子性实现。完整恢复可靠性仍未实测。

## 后续波次：sqlite-utils

sqlite-utils 很适合提供真正不同的数据工程场景：CSV/TSV 导入、SQLite schema/NULL/类型推断、全文索引、转换回调和 CLI 数据路径，比再堆 TinyDB 新增便捷 API 更有覆盖价值。首轮宜同样改为按真实问答分场景，保留“前导零丢失”需要明确类型策略/无需默认改库的结论，不能照搬旧20步全修改路线。

两项真实修改目标已具备原版证据：

1. `Table.enable_fts(columns: Iterable[str], ...)` 在 `db.py:3754` 构造SQL、populate和trigger多次消费columns；列表4组合通过、一次性iterator4组合报SQL语法错并遗留fts表。最小产品允许路径可为 `library/sqlite_utils/db.py`，相关公开 `library/tests/test_fts.py`；native以真正FTS4/FTS5初始与增删改命中验证，不能只查返回值。
2. `Table.convert` 在 `db.py:4177` 以函数名注册包装回调，`Database.register_function` 在第793行默认保留同名同arity旧回调；dict.get/partial/可调用对象/同名普通函数4类第二次把country写成NULL，lambda对照正常。最小产品同 `db.py`，相关公开 `test_convert.py/test_register_function.py`；native核两列、跨表、lambda与公开replace语义。

选择后续的原因是依赖和回归准备稍重，不是功能或质量不合格：运行依赖click、click-default-group、pluggy、python-dateutil、sqlite-fts4、tabulate、pip；完整上游宿主峰值约285 MiB超出business 256 MiB、25秒接近30秒，必须在现有regression profile正式测余量。可选扩展有16项既有skip，需要冻结明确适用集合和理由，不能为追求全绿偷偷删除。在1536 MiB账号预算下串行、受控regression profile合理可行是**推断**，当前实际部署镜像中的完整基线未测。

## 实现交接清单与未完成项

1. 先核最终任务包约定与入口依赖，freeze这12项真实任务；新增材料、源码路径、rubric/native说明均按现有schema制作，不改schema凑表达。
2. 固定TinyDB源码完整清单/commit/license，排除 `.git`、venv、旧研究日志；候选只拿公开library/app/materials，上游tests可见，oracle不见。
3. 取当前正式账号镜像，离线依赖精确版本+SHA冻结；显式检查候选模块导入路径、原始源码摘要、Python环境，不允许从旧venv导入TinyDB。
4. 实现2修改的参考补丁与私有native，先固定原版失败/参考通过/反例拒绝；保护列表旧语义与map不缓存，回归固定完整上游集合。
5. 非修改项只在有可执行交付时校验答复代码；其余fact/native探针只作为语义事实依据，答复评分必须独立，不混淆判定层。
6. 全包模拟执行明确回答/语义评审/token为模拟；真实native与内容失败/参考通过、完整回归、材料披露、无代码checkpoint、UI中英文和预算/timeout分别留证。

截至本研究结束：本轮模型调用0、正式内容变更0、产品变更0、完整基线重跑0、生产操作0。尚未做12项可执行内容、私有oracle或参考解；本轮有效新增执行仅7个宿主微探针。后续工作应以子任务 `.trellis/tasks/10-21-project-catalog-pilot-pack` 的planning产物及用户审查为准。
