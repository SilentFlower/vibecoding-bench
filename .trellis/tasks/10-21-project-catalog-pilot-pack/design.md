# 首批三项目内容包设计

## 既有能力与新增边界

复用 `ProjectLibrary` 内容 schema 2、policy 3、现有五类任务、私有语义评审和 `ProjectVerifier.verify_native`。新内容不增加 DTO、路由、表或运行阶段，不改线上账号。实际接入签名、字段与限制见 `research/integration-contracts.md`。

新增正式路径为 `project_library/projects/{tinydb,jinja,schedule}/` 和各自 `project_library/environments/<project>-py312/`。每仓沿用 `project.json/seed/library/materials/disclosure/verification` 布局。现有三个项目及其环境保持字节不变；只给 catalog 新增三个 key、更新内容版本和相应总览说明。

## 固定来源与任务矩阵

| 项目 | 固定上游提交 | 场景／任务 | 理解／咨询／诊断／方案／修改 |
| --- | --- | --- | --- |
| TinyDB | `edff96aeb2616402e9489d46e90a592c05565621` | 4／12 | 2／3／3／2／2 |
| Jinja | `5ef70112a1ff19c05324ff889dd30405b1002044` | 4／12 | 1／3／4／2／2 |
| schedule | `82a43db1b938d8fdf60103bd41f329e06c8d3651` | 5／13 | 2／3／4／2／2 |
| 新增合计 | 三个唯一上游项目 | 13／37 | 5／9／11／6／6 |

业务分组与英文首问／中文目标的权威来源是母任务 `research/data-candidates.md`、`document-candidates.md`、`operations-candidates.md`；本任务不能把这些文本误当已经创建的材料或验收资产。

- TinyDB：订单接入、查询分诊、批量规则、落盘与恢复方案。稳定任务前缀 `TD-`。
- Jinja：报表接入、输出异常定位、两个过滤器修复、批量生成与导出边界。稳定前缀 `JI-`。
- schedule：调度接入、迟到／缺少运行、异常与取消、批量执行尾等待、未配置任务展示。稳定前缀 `SC-`。

全部 31 个非修改任务 `allowed_paths=[]`。其中只问解释或方案的任务依赖私有语义判定；要求最小可运行示例的咨询题增加实际候选上的代码执行。不能因为问题本身无需改代码就自动判通过，也不能用固定事实探针替代回答质量。

## 材料、入口与实际依赖

入口只用现有 `entries/task_ids/materials/setup`；披露只用现有 `branches/when/materials/setup/activate_tasks`，不新增研究中的 `state/hypothesis` 公开字段。

- TinyDB `TD-D01`、Jinja `JI-D01`：正常入口允许先请求材料再诊断；另有材料确实无法提供的入口，以 `insufficient_information` 为合法结果。无材料入口不得向候选或评审泄露正常分支的私有复现。
- TinyDB `TD-P01`：缺少重复 SKU 规则时先请求冻结的需求补充，再完成方案；同任务正常披露不额外计一次任务或修正。
- schedule `SC-D03`：先请求回调、调用及完整异常，再投放固定业务材料，最后解释默认异常传播。
- TinyDB 两修改各位于自己的场景：默认清单按研究顺序先诊断再修改，直接修改入口自带完整复现且 `requires=[]`。两个场景各用独立原版工作区，分别跑完整回归，不跨场景隐式继承。
- Jinja 两修改位于同一场景。默认入口依次诊断、Mapping 修复、map 默认值修复；M01 的完整材料自足，不强造诊断 answer 依赖；M02 声明对 M01 的 `code` 依赖，验收必须复验已接受 Mapping 能力。诊断限定原版输入或被冻结复现材料，避免读取修复后源码还要求复现旧结果。首批不增加绕开这一接受依赖的独立 M02 入口。
- schedule M01 只依赖同场景 D04 的回答，M02 只依赖同场景 U02；两场景独立起点，各跑完整上游集合，不把 M01 checkpoint 传给另一场景。

材料无法提供的入口必须冻结明确的英文业务记录，说明所请求的复现材料确实无法再提供，不能仅用入口 ID 暗示这一事实。分支条件与 rubric 根据实际消费的记录判定合法结果。现有 `verify_native` 不接收 entry 参数；保留 native 时，只检查可见冻结材料能够支持的路径或通用事实，不假定获得入口身份。正常路径的私有复现不能作为通用 `source_evidence` 传入无材料评审包。

## 六项工程交付

| 任务 | 实际改动范围与边界 | 独立验证 |
| --- | --- | --- |
| TD-M01 | `library/tinydb/queries.py` 与对应公开查询测试；不改变 storage/API | 两字段路径、双查询顺序、Memory／JSON、缓存正常收益、根级／组合／不可缓存 map 路径 |
| TD-M02 | `library/tinydb/table.py` 与公开批量更新测试；只保证有限规则枚举完整后才应用 | list/tuple/iterator/generator 等价、顺序／重复 ID、两 storage、枚举中途异常不部分写入；不扩展为任意回调事务 |
| JI-M01 | `library/src/jinja2/filters.py` 与公开 filter 测试 | dict／UserDict／标准 Mapping、Unicode 和空键、pair 重复键、字符串路径原行为 |
| JI-M02 | 同上；保留 M01 接受的行为 | 显式 None 与未给 default 区分、False/0/空串、同步／异步、嵌套和共享 getter 其他调用方 |
| SC-M01 | `library/schedule/__init__.py` 与公开原生测试 | 0／1／3 任务无尾延迟、任务快照、回调顺序／参数、取消和异常传播 |
| SC-M02 | 同上，但独立场景基线 | 默认未配置 Job 可 repr、interval2对照、无隐式单位／注册／执行、配置后表示保持兼容 |

实际 `allowed_paths` 需按完整候选根写 `library/...`；研究文档里的仓库相对路径不得遗漏前缀。原版 seed 不预先修复；私有 reference、patch 和固定验收从候选输入完全隔离。

六项修改均要求交付有意义的公开回归用例，因此在 native 与上游回归之外声明 `evaluation.semantic=true`。私有 rubric 明确授权引用候选实现及公开测试文件，检查其断言和覆盖目标；不能只因独立行为通过就忽略用户要求的测试交付。该检查仍沿用同实际模型评审，模拟阶段只证明协议可运行。

## 原生环境与回归

每仓冻结精确 Python 3.12 补丁版本、完整实际依赖版本、兼容 wheel 和 SHA，业务／回归档案分别测量。首选已发布的 `ci-39609484070-1` account 镜像进行准入；其下载和依赖准备不执行模型推理。具体 profile 不以宿主 3.12.3 的旧测量替代。

共享 `orchestrator/project_native_regression.py` 为可信实现来源，新增三个受控 suite。Jinja 需要可选物理实现目录 `src/jinja2` 和导入根 `src`，模块名仍为 `jinja2`；旧三个 suite 沿原默认。校验这些配置为固定相对路径并实际核对候选 import 路径，禁止落到安装库。私有插件、baseline 测试／配置与节点合同仍固定，不能让候选新增 pytest 控制改变收集集合。

新增三项目 `verification/` 采用本轮可信脚本副本并核对 SHA；旧三项目私有脚本和合同不动。历史 228／911／81 仅为预估参照，当前镜像须重新完整收集和执行才能冻结合同。新套件不能接受“节点少了但退出码为零”。

可执行原生示例只在无网络、UID1000、只读来源的验证容器运行，不在控制端执行候选；片段提取复用现有明确单代码块模式。项目源码对象、离线依赖和临时运行目录分开，控制端持有完整私有 oracle。

## 版本、语言与交付字节

版本计划为 `real-project-scenarios-v3-en`；内容 digest 必须由实际完整字节计算。保留三仓原 ID／目录和旧发布；独立测试根同时安装旧／新版本，模拟当前库不在时历史仍可读取。

英文首问、分支说明、材料指令、rubric 逐项检查；中文 `summary(include_steps=True)` 的 title／description／scenario goal／task goal 与规划逐字对应。业务字面、原始报错和上游注释不为了语言统计而篡改。

正式内容已有 `project_library/** -text`；本任务新增冻结研究证据仅增加精确任务路径规则。Git 导出和 Docker source snapshot 均核文件全集、逐文件 SHA 和实际内容库 digest。若上游含被忽略的公开 `.env`、AGENTS.md 或链接，先按固定来源清单判定再做精确处理，不放开全局忽略规则。

## 模拟集成与限制

先校准所有原生目标和参考，再用空库、合成账号、mock 候选／评审跑三十七默认任务及合法物料变化路径。采用现有 Scheduler／driver／tmux 和原生 verifier，固定业务计时保持真实；schedule 假时钟仅控制其业务子进程。页面、API、SQLite 互相核对真实结果、非修改检查点为零、Jinja 接受父链、披露不多算业务尝试和候选／评审用量覆盖。

既有三项目版本已经上线，本轮六项目内容仅完成本地验证，不在本子任务自动部署。完成代码、内容和本地证据后进入项目完成链，再按实际用户授权提交与发布。真实模型质量、真实评分可靠性和 token 成本保持未验证。
