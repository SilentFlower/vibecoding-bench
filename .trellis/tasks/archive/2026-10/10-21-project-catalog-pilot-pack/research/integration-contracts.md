# 首批内容包的既有接入契约

## 当前边界

当前子任务为 `.trellis/tasks/10-21-project-catalog-pilot-pack`，已完成本地交付并写入 completed／closed。本文记录接入契约；实现与验证证据见 `integration-report.md`。本地内容为六项目、二十六场景、五十七任务，线上基线仍为 `ci-39609484070-1` 的三项目、十三场景、二十任务，本轮尚未部署。

## 实际入口

- `ProjectLibrary.__init__`：`orchestrator/project_library.py:220`。schema 2 只要求至少一个项目，不使用 legacy 100 项目／20 步下限；逐项目核 seed、项目树及环境制品摘要。
- `validate_scenario_project`：`orchestrator/project_scenario_content.py:78`。入口任务必须可达，依赖仅同场景无环，code 依赖只能引用 modify。五类类型为 `understand/consult/diagnose/plan/modify`。
- `_validate_task`：同文件 `:177`。任务必须显式声明 `goal/prompt/requires/allowed_paths/outcomes/evaluation`；modify 要求非空授权路径及 native 定义。材料分为公开 materials 与私有 disclosure。
- `validate_environment`：同文件 `:296`。必须冻结精确 Python、非空精确 requirements、非空 artifacts 及逐文件 SHA；业务和回归资源独立声明。纯标准库项目同样需要真实测试依赖，不能用假 wheel 或空 requirements 越过校验。
- `ProjectVerifier.verify_native`：`orchestrator/project_verifier.py:212`。候选、baseline、私有检查、离线环境只读挂载，在同批 account 镜像内 UID1000、无网络、只读根执行；环境准备失败与业务失败分开。
- `verify_native` 不接收 entry 参数。无材料入口需以冻结业务材料明确记录无法提供的事实；原生检查不能假定取得入口身份，通用评审证据不能夹带正常路径的私有复现。规划交叉复核见 `planning-review.md`。
- `scripts/validate-project-library.py` 的 schema 2 统计已经动态计算，不需要把三改成六的数量硬编码。
- `scripts/validate-project-scenarios.py` 已支持 `--root/--project/--task/--candidate/--answer/--entry/--branch/--expect/--with-regression`；不得另造一套宿主执行候选的验收入口。

## 必需的原生回归适配

规划时 `orchestrator/project_native_regression.py` 的 `SUITES` 只有原三仓，`_overlay` 默认实现位于 `candidate / package`，`_run` 默认把项目根放入 PYTHONPATH。本轮已增加三套 suite 及受控实现目录／导入根；不能仅复制新项目 manifest 后宣称工程回归可运行。

TinyDB 和 schedule 的实际包目录分别为 `tinydb/`、`schedule/`。Jinja 实现位于 `src/jinja2/`，导入模块为 `jinja2`：包名与物理实现目录必须分开，不能把 `src/jinja2` 传给 `import_module`，也不能从提前安装的 Jinja wheel 偷换候选源码。

采用最小向后兼容扩展：保留原三个 suite 的默认字段及行为，为新 suite 增加受控实现目录／导入根描述；新增三个 suite 的 pytest 参数、插件和预期节点需在目标镜像重新校准。延用原版配置／测试恢复、pytest 控制文件保护、原生 import 路径核对、完整节点集合和结果合同。

可信回归入口仍由项目 manifest 的 `evaluation.native` 引用固定 `verification` 内容。现有三个项目的私有脚本与合同保持原样；新增内容中的脚本副本须与本轮可信实现一致，并留下摘要及同步校验，不能把旧脚本原地改写成新版本。

## 证据层次

| 证据 | 能证明 | 不能代替 |
| --- | --- | --- |
| 既有研究原生基线 | 固定版本曾在报告所述环境正常运行 | 当前正式镜像的回归合同 |
| 本轮原版最小复现 | 单个公开行为或缺陷在固定代码上存在 | 完整上游集合回归 |
| 静态内容加载 | 来源字段、结构、材料／wheel 摘要、数量可加载 | 业务正确性、模型质量 |
| 独立 native | 实际候选的 API、示例、文件结果及可执行断言 | 文字论证是否可靠，语义评审 |
| 原生回归合同 | 固定测试／插件／节点及候选导入正确 | 新需求独立业务验收 |
| mock 调度与 UI/API/DB | 输入消费、披露、恢复、状态和用量投影 | 真实模型回答质量、真实 token 成本 |

所有修改目标都要同时保留原版预期失败、私有参考候选通过及正常／反例证据；参考实现与答案不能进入候选 seed、材料、公开目录或评审前用户输入。

## 字节保真、资源与历史

- `project_library/** -text` 已覆盖正式新内容；新任务研究如保存冻结代码／合同，需补精确任务路径的 `-text` 规则。候选原始环境及日志放忽略的 `.deploy/project-catalog-pilot-pack/`，不放进待运行源码。
- `.gitignore` 的 `.env` 与 AGENTS.md 例外当前仅服务固定老项目；如新仓跟踪同名文件，先按真实清单取证，再只为必要的公开来源文件增加精确例外，不批量开放。
- 当前部署账号 RAM 为 1536 MiB。候选、network、sender、评审份额不变；业务／回归 profile 必须在准入时实测，不因为历史 RSS 很小就宣称已适配当前镜像。
- 新内容库版本为 `real-project-scenarios-v3-en`，实际 digest 由完整字节重算为 `876b7a545471dd2ffd61f09ecb11427820765803049aedc2956c1cb23c77c2a8`。旧三仓内容树和环境保持不变，独立测试数据根已同时 install 旧／新版本并验证历史按旧 release 读取。
- 只运行合成账号与 mock CLI，真实模型与 OAuth 调用保持 0。语义评审始终使用同实际模型；本轮不会为制作内容寻找第二模型或启用旧账号。

## 实现所有权候选

三个项目内容、各自离线 profile、私有验收、校准证据可以按项目并行编写；共享回归模块、catalog、项目说明、语言／数量集成检查由主代理串行整合。现有 277 个计划外未提交文件继续保留，研究索引旧统计不原地重写。
