# 第二批内容包接入契约与技术边界

本文记录实际已读接口与规划适配点，不是四仓已经准入的证据。当前正式源码仍为v3-en的6项目／26场景／57任务。

## 实际可复用入口

- `orchestrator/project_library.py` 的 `ProjectLibrary` 加载、install、逐项目快照与版本历史继续复用；schema2不继承旧100项目／20步门槛。
- `project_scenario_content.py:78` 的 `validate_scenario_project(root, manifest, key)` 校验固定来源／许可、同场景DAG及入口可达；`:177` 的 `_validate_task` 要求显式 `requires/allowed_paths/outcomes/evaluation`，修改必须非空路径和独立native。
- 同文件 `:296` 的 `validate_environment(root, key)` 读取 `environments/<key>/profile/profile.json`，固定精确Python、requirements、非空真实artifacts及逐SHA；business／regression各自声明timeout_sec／memory_mb／pids_limit。合法结构不能替代当前镜像实测。
- 同文件 `scenario_summary(..., include_tasks=True)` 仅投影中文title／goal及稳定身份／依赖，隐藏prompt／branch／rubric；本批不新增DTO、API、DB列或页面协议。
- `scripts/validate-project-scenarios.py` 的 `validate(args, data)` 实际支持 `--root/--project/--task/--candidate/--answer/--entry/--branch/--expect/--with-regression/--regression-only`；先校验所选入口包含当前任务，给定候选已改的业务文件不会被setup覆盖。native接收answer和冻结内容，不接收entry身份，不能依赖不存在的参数识别无材料路径。
- `ProjectVerifier.verify_native(candidate, project_root, specification, environment_root, profile, *, answer='', regression=False)` 继续在同批account镜像、UID1000、无网络、只读来源与无真实账号凭据的环境执行。业务／回归资源分别选择，不能在控制端执行候选。

## 可信回归适配

`orchestrator/project_native_regression.py` 当前只有六套SUITES；本批需新增四仓真实模块／实现目录／导入根／pytest参数和插件。沿用 `_suite_paths` 的相对路径及模块对应校验，候选实现与父目录拒链接；baseline固定测试、配置和控制hook保持可信。当前镜像需先实际收集非空适用集合并执行，再冻结合同，不能从旧报告复制计数。

当前 `_run` 将collection主节点数、唯一节点数与JUnit testcase元素数作严格相等校验，逐主节点合并setup／call／teardown。Tenacity历史XML已实际重数：suite的tests属性为200，但testcase元素只有185，日志为185主项和15子测试；不能仅凭汇总属性推断现有相等校验冲突。实现先在目标镜像核本仓pytest／subtests格式，保留严格主节点比较；仅在新Tenacity套件补充可核对的真实子测试数量、父节点／上下文及结果证据，不能删子测试或放松为大于等于。旧六仓默认和冻结私有脚本保持不变。

新增四仓的私有runner副本与本轮共享可信实现逐SHA一致；既有六仓不原地升级。定向测试覆盖正常新布局／插件、错误导入、保留固定测试控制及子测试成功／失败／缺失对账（仅实际新增该适配时），原有六项兼容断言继续保留。

## 环境与素材隔离

- 镜像基线沿用 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39609484070-1`；首批实测Python3.12.15，但本批仍需读取实际解释器／RepoDigest，不把tag或历史Python当新实测。
- 原生profile可从现有512MiB／180秒回归档案起步实测，最终值以当前镜像资源证据为准；不增加1536MiB账号预算，不因sqlite-utils旧峰值约285MiB就宣称business256MiB完整测试可过。
- dotenv只使用专用合成.env与显式路径，CLI入口及Click／IPython回归也须离线可用；不查找宿主祖先配置。
- `_NATIVE_EXECUTE` 实际创建独占 `/work/python` venv并把其bin加入PATH，`verify_native` 的 `/work` 为rw,exec，`/tmp`无exec声明。共享回归已有Typer的受控纯路径.pth与退出清理模式；dotenv新增入口应由可信固定目标生成在本次可执行环境、绑定本轮src树，验证实际直接调用dotenv的上游测试，不能仅以python -m替代该入口或依赖已安装发行包。
- TOMLKit保留实际Git子模块版本、许可及测试素材，不能用空目录替代toml-test；源码与测试文档中的原始字节不格式化。
- Tenacity同步／异步测试依赖、浮点与自定义策略边界均需冻结；业务fake clock／sleep仅在验证子进程，不控制平台driver计时。
- 首问的通用rubric不能夹带尚未消费的隐藏复现。只读任务没有candidate_files时，不设置无静态证据却要求候选文件引证的flag；每个披露与unavailable都先跑真实构包／parse_review协议预检。

## 版本、统计与交付

计划新增 `real-project-scenarios-v4-en`；实际digest只在内容完整后重算，任务数由四仓去重表汇总。默认路径、合法入口、披露和模拟Run分别对账，不把分支路径数当唯一任务数。

保留旧六项目／六环境的完整文件SHA、稳定ID和历史release；临时Git导出与正式Docker忽略规则核对内容全集，新增研究路径按精确范围保留原始字节。旧277个无关dirty维持原状。历史新旧版本实际共存，当前catalog不可用时新建拒绝但历史仍读其固定release。

本批候选／评审为mock，原生业务与冻结回归真实执行。覆盖所有新增默认任务及影响材料／结果的分支；桌面／390px、明暗主题及页面／API／SQLite一致，用量与预算从精确原生日志和实际消费重算。最终分别报告内容、模拟、真实模型、生产部署，不自动Git或上线。
