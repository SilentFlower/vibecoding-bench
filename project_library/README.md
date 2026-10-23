# 真实项目完整开发任务库

内容 schema 3 以一个真实需求或 BUG 的完整开发周期计数。现有 100 个项目均已重审：30 个项目归并为 36 项工程任务，另 70 个项目缺少独立工程交付合同与正反验收，明确保留为待准入。旧 726 项问答与研究中的 2,000 项提案均不直接计作新任务。

同一任务在原开发者会话和工作区内完成源码调查、深入追问、方案确认、实施、验收和必要修复。需求方由一次外部 API 调用生成下一条消息，依据实际回答推进，没有固定问答轮数。普通交流不启动独立评分；实际交付才运行控制端原生行为、冻结上游回归和最终交付审查。

| 项目 | 完整任务 | 工程目标 |
| --- | ---: | --- |
| python-frontmatter | 1 | 修复合法保留键元数据的读取冲突并保持兼容 |
| pydantic-settings | 1 | 修复库内字典Union分段环境解码并补回归 |
| typer | 1 | 为用户商品应用增加完整JSON清单导出并保留既有行为 |
| tinydb | 2 | 让 fragment 缓存身份包含完整字段路径；让有限一次性规则与列表规则更新结果一致 |
| jinja | 1 | 修复过滤器对 Mapping 输入和显式 None 默认值的兼容行为 |
| schedule | 2 | 修复批量执行的尾等待并保持快照与取消语义；安全展示未配置任务并保留已配置格式与状态 |
| python-dotenv | 2 | 保留 set/unset 非目标记录的原始换行；跨行键在打开或创建文件前失败 |
| tomlkit | 2 | 修复 Array 的 *=，保留文档绑定、合法格式和现有数组操作。；删除叶子时保留仍存在的空父表，不影响普通 inline 删除的既有排版。 |
| sqlite-utils | 2 | 修复有限一次性列配置的全文索引行为；确保每次转换使用当次传入的回调 |
| tenacity | 2 | 零指数贡献保持下界和抖动，不误跳上限；迭代求值内置组合树，同时保留分组与自定义策略 |
| cachetools | 1 | 修复类访问关键字receiver并保护原调用合同 |
| xmltodict | 1 | 支持同步分块Iterator并保留消费边界 |
| tabulate | 1 | 统一tuple排版序列并保持原有输出 |
| click | 1 | 展示有序错误附注并保护既有CLI输出 |
| cli-helpers | 1 | 隔离每次格式覆盖并保持注册默认 |
| mistune | 1 | 修复空文档CLI并保留真实输出副作用 |
| boltons | 1 | 修复falsey key并保护分组和错误语义 |
| path | 1 | 修复用户块取消时的原文件恢复 |
| dpath | 1 | 修复过滤删除越过路径范围的问题 |
| alive-progress | 1 | 让合法假值回调完成一次收尾 |
| jmespath | 1 | 修复嵌套JSON比较混淆布尔和数字 |
| confuse | 1 | 修复文件重载后已删除配置仍残留 |
| simplejson | 1 | 避免CLI在输入错误时截断已有输出 |
| marshmallow | 1 | 拒绝日期字段隐式接受时间对象 |
| inflect | 1 | 避免未知模式键导致部分状态更新 |
| xlsxwriter | 1 | 让通用写入的公式禁用覆盖数组字符串 |
| ftfy | 1 | 修复关闭解释时丢失编码配置 |
| feedgen | 1 | 修复Atom条目链接元数据丢失 |
| tablib | 1 | 修复商品字典记录的字段错位 |
| sqlglot | 1 | 修复血缘图展示污染原SQL |

## 内容与历史

- `catalog.json`：当前内容版本、可执行项目和逐仓准入摘要。
- `catalog-development.json`：完整开发周期目录；`development-audit.json` 保存全部 100 项目的来源、旧任务逐项映射与阻塞原因。
- `catalog-v37.json` 和各项目原 `project.json`：保留 schema 2 的 100 项目、426 场景、726 项旧任务定义。运行中的历史批次继续绑定原冻结 release。
- `projects/<key>/development.json`：完整任务的背景、目标、授权范围、公开材料、需求方材料及最终验收引用。每个场景只有一项完整任务；Jinja 的代码依赖归入同一过滤器兼容性修复。
- `seed/`：固定真实上游源码、应用和许可证，保持原来源与摘要。`materials/` 是公开输入，`disclosure/` 是需求方可以依据事实补充的业务材料。
- `verification/`：控制端私有 rubric、独立业务断言、冻结回归合同及可复核参考补丁；这些文件不进入开发者工作区或外部需求方请求。
- `environments/`：固定 Python、资源、精确依赖与离线制品；新周期复用既有原生环境。

项目名称、阶段和页面为中文；实际模型对话使用任务原有语言，固定业务字段、原始错误与代码保持原文。70 个未准入项目仍保留真实源码、许可证、旧材料和逐仓研究，不能在页面中选择执行。

## 接入与恢复

服务端配置 `PROJECT_REQUESTER_BASE_URL`、`PROJECT_REQUESTER_API_KEY`、`PROJECT_REQUESTER_MODEL` 和 `PROJECT_REQUESTER_FALLBACK_MODEL`。指定服务为 `https://ai.flower-cli.com/v1`，主模型 `gemini-3-flash-agent`，备用 `deepseek-flash`；这些环境变量作为未设置页面覆盖时的初始值。也可在项目页“外接需求方模型配置”动态编辑一个 Base URL、API Key 和按优先级排列的 1～8 个模型，保存后无需重启。密钥在控制端 `settings/project-requester.json` 中以 0600 原子保存，读取接口仅返回是否已配置；密钥留空沿用已有值，可恢复环境配置。密钥不能写入本库、任务、浏览器响应或导出报告。

主模型额度不足、429 或暂时服务故障时按模型列表有限降级，同一配置版本内当前任务后续沿用已选模型；页面修改配置后按新的优先级重新选择。认证或参数错误直接显示。主备均不可用时保存任务和待生成消息并有限恢复，不形成业务失败。生成的有效消息先持久化，再复用原投递机制；中断后复用已生成消息，不重新生成或重复投递。

单次执行超时保留原 Run 的 timeout 和原工作区，预算允许时优先续做同账号的可恢复任务。累计任务预算包括开发者、最终评审和外部需求方的实际工作时间与未决预留；排队与独立原生程序验收另有既定上限。业务修复最多两次，同版本语义异议只复核一次；程序失败不能靠语义评审覆盖。服务恢复、业务修复和异议分别计量。

暂停、停止、原生消费不确定、身份变化或会话／工作区缺失遵守既有门禁。外部请求中断且结果未知时保留预留并阻塞盲重发。页面按需展示连续对话，开发者、需求方、最终评审用量单列；缓存按真实服务证据展示，缺失统计保持未知。

## 本地验证

```bash
.venv/bin/python scripts/validate-project-library.py
.venv/bin/python scripts/validate-project-library.py --catalog catalog-v37.json
.venv/bin/python scripts/validate-development-content.py --image <本地账号镜像> --data <全新独立证据目录>
```

结构校验不代表业务或模型完成。完整准入命令在无网络、无凭据的 Docker 中逐项核原版失败、参考交付通过、授权范围及完整冻结回归，参考补丁只在控制端使用。单项验收继续使用 `validate-project-scenarios.py`，任务 ID 取实际 `development.json`，可指定 `--catalog`；新内容不使用旧 `--all` 参考运行时。

`build-project-development-content.py` 从保留的原定义重新生成逐仓映射与完整合同；`--activate --validation-report <当前全量原生回执>` 仅在摘要和任务覆盖完全一致时切换本地目录。它不补造新的缺陷、运行模型或部署服务。

Click 需求和 Cachetools BUG 的完整周期可通过 `verify-project-development-pilots.py --image <镜像> --library-root <双试点内容根> --evidence-dir <证据目录> --browser` 验证。该工具使用本机 HTTPS 需求方替身、合成开发者与语义评审回复、真实 SQLite／原生交接及真实 Docker 验收，并在 Chrome 核页面和 API；不代表真实模型质量、成本或缓存已验证。

部署、真实账号任务与真实外部业务调用分别授权及留证。项目运行合同见 [项目迭代规范](../.trellis/spec/vibecoding-bench/backend/project-iterations.md)。
