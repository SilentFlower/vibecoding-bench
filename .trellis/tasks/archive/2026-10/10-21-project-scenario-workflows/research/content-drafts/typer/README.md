# Research: Typer 正式场景内容草案与校准

- Query: 按实际 schema 2 格式物化 Typer 的 4 个场景／7 个任务，保留真实源码、正常行为诊断与用户应用增强边界。
- Scope: internal
- Date: 2026-10-21

## Findings

本目录是供主会话审核集成的内容草案，不直接修改正式 catalog。固定来源为 `fastapi/typer@a5882dedf0bc7a46cd861fdfca020f88519e0f21`、Typer 0.27.3；内容依据逐项来自 `research/project-scenarios/typer.md` 及实际源码定义。

### 内容与保护边界

| 场景 | 任务 | 交付 |
| --- | --- | --- |
| TY-S01 商品选型与接入 | TY-U01 理解；TY-C01 咨询 | 用途、构造流程、持久化边界，以及只在答复中给出的可运行示例 |
| TY-S02 命令与选项排错 | TY-D01、TY-D02 诊断 | 两项均为正常行为；D02 必须先请求必要材料再完成判断 |
| TY-S03 类型能力及方案 | TY-C02 咨询；TY-P01 方案 | 辨识现有 Literal／parser／click_type，比较两个本地命令的 SKU 方案 |
| TY-S04 商品导出 | TY-M01 修改 | 仅增强用户应用，保留 product，独立验输出文件、拒绝路径与文件边界 |

- `seed/library/` 是干净真实上游：776 个文件、2,084,485 字节，与旧研究规模记录一致；逐文件 SHA256 见 `provenance/source-files.json`，源码字节不改。
- 复制排除了 `.git`、`.pdm-build`、`.pytest_cache`、`__pycache__`、`coverage` 等生成目录，没有 venv、字节码或符号链接；上游自身 `.env` 等真实文件保留。
- 主 MIT、vendored Click BSD-3-Clause 及 `_typing.py` Pydantic 来源说明均保留；另保存 `seed/PYDANTIC-v1.9.2-LICENSE.txt`。没有把主 MIT 当作所有附带内容的唯一许可。
- `seed/app/` 为空起点。所有任务保护 `library/`；只有 TY-M01 授权 `app/shop.py`、`app/tests/`、`app/README.md`，`app/catalog.json` 仍受保护。
- TY-P01 只依赖 TY-C02 的回答产物，不声明代码依赖；重试、材料披露和用户测试不增加任务数。

### 按需投放与隐藏材料

`project.json` 使用当前校验器真实的 scenarios／entries／tasks、requires、materials、allowed_paths、outcomes、evaluation、branches 字段；由主会话确认的 `setup=[{source,target}]` 只在首次准备时物化一次。

- TY-U01／TY-C01 不创建应用文件。C01 的业务函数作为可见材料提供，受评模型只返回示例。
- TY-D01 完整 `materials/TY-D01/shop.py` 作为可见代码材料，不落盘为 D02 的应用；控制端在隔离临时目录验证这份单命令夹具。
- TY-D02 首轮没有注册代码或隐藏应用文件。只在 `TY-D02-registration` 合法披露后提供 `disclosure/TY-D02/` 的注册代码、追问及同一代码生成的真实 help，并一次性物化 `app/shop.py`。
- D02 首轮请求注册代码、根或子命令帮助均可触发同一材料组；首轮武断结论不能通过，仅合理提问也不是整个任务完成。
- TY-M01 的 task setup 在任务首次准备时从 `materials/TY-M01/` 发布独立 APP-R0、catalog 与说明，不继承其他场景代码；与当前校验器的 task/materials 前缀一致。
- `verification/`、完整 rubric、参考实现、补丁及 provenance 均留在控制端，不复制进候选工作区。

### 原生脚本和参考候选

5 份 `verification/native/*.json` 使用已确认接口：`script,args,python_paths,expected,resource_profile`。脚本为自包含的 `verification/native_checks.py`，因为现有适配只复制指定控制脚本，不假定整个验证目录对候选可见。

控制端注入 `PROJECT_CANDIDATE_ROOT=/work/project` 和 `PROJECT_ANSWER_FILE=/request-data/answer.txt`；脚本也支持显式 `--candidate-root/--answer-file`，用于校准，不引入未经支持的参数占位。

C01 从被冻结的 UTF-8 回答中识别完整 Python 主程序，语法等价代码去重，必要时组合碎片；多份不同完整主程序拒绝歧义，不任取首块。示例仅在验证端临时目录运行，不要求模型写 `shop.py`，也不接受为工程检查点。

所有子程序限时 8 秒、stdout／stderr 各限 64 KiB，业务终端宽度固定 80，控制脚本输出单一业务 JSON。检查真实 `typer.__file__` 必须来自候选 `library/`，不能偷偷导入已安装的另一份 Typer；帮助信息还要求真实退出码为零。

`verification/reference/APP-R1.patch` 只修改用户应用、测试及说明；参考 `shop.py` 可供主会话校准可达性，不修改上游。控制脚本实际验证成功输出、中文和顺序、字段筛选、坏输入及无部分文件、禁止覆盖、输入不变、product 与帮助回归；不是仅检查用户测试或“成功”文字。

工程 native JSON 另列适用完整原生回归命令与资源档案。业务观察和完整原生回归的执行结果分别记录，不能只运行一个脚本便声称全套通过。

### 已有实证与运行边界

- `validation/static-check.json`：schema 校验通过、4／7 数量正确、776 个上游文件逐字节一致；自写脚本及嵌入 Python 语法已解析。
- `validation/local-business-calibration.json`：使用已存在的宿主 Python 3.12.3 venv，咨询、单命令、根选项、自定义类型共 4 模式匹配冻结结果；APP-R0 导出目标未满足，APP-R1 参考候选全部业务观察匹配。
- `validation/consult-negative-calibration.json`：放过负数、没有可运行示例、两份不同完整程序三种错误／歧义答案均被拒绝；不是只要出现正确 API 名称就放行。
- 首轮校准驱动错误地解引用 venv 解释器导致依赖缺失，已纠正；失败记录保留在 `validation/initial-host-interpreter-resolution/`，不冒称 Typer 缺陷。
- D02 help 已由固定注册代码真实执行生成，没有手编帮助输出；宿主结果仍与目标镜像结果分开。
- 固定依赖与目标镜像取证已完成，入口为同任务 `research/environment-drafts/typer-py312/verification-summary.json`：实际 Python 3.12.15，完整原生 1,481 通过／22 普通 skip／2 XFAIL，零失败，187.781728 秒；额外 6 次业务正反校准、3 个错误咨询答案和参考用户测试均符合冻结预期。
- 正式集成使用 `environment-drafts/typer-py312/` 核验后的 profile 与 16 个真实 wheel。这里 `environment/` 保留最初仅依赖清单的草案，不能当作已有离线制品。首轮环境问题及超宽 help 修正均留原始记录，没有改库／减测试或重复已通过的全套。
- 本轮模型调用和模型完成数均为 0；代码参考候选通过不代表受评模型已经解决 TY-M01。

### 读取的实际定义与证据

- `library/typer/main.py:890`：command 装饰器保存 CommandInfo；`:1173`：单命令与 callback／group 构造条件；`:1530`：parser、click_type、IntRange、Literal 等实际映射；`:1632`：参数注解与元数据转换。
- `library/typer/models.py:336`：parser／click_type 互斥；`library/typer/core.py:1077`、`:1113`：根参数解析与子 context；`library/typer/_click/types.py:124`：ValueError 进入参数转换失败。
- 读取 custom_types、one_or_multiple、callback 实例，`tests/test_type_conversion.py` 的成功／ValueError／自定义类型测试及 `tests/test_others.py` 的互斥测试。
- 依赖精确版本和下载 SHA 来源是历史 `installation.json`、`requirements-frozen.txt`；来源、许可与旧基线的引用见 `provenance/source.json`。旧 1,481 主项、22 skip、2 XFAIL 不冒充这轮目标镜像结果。

## Caveats / Not Found

- 主会话仍需审核新内容、一次性 setup／分支披露的集成和 profile 真实落点；本目录不是正式 catalog 已发布的证据。
- 目标镜像环境和原生／业务校准已有独立证据，正式原生适配仍需复现独立 venv、候选源码 `.pth` 注册、真实 Bash 祖先及 `/work` 允许加载 C 扩展的属性；不能把任意不同启动方式当成已经验证等价。
- 同模型语义评审质量仍须独立校准；这里的原生观察和参考回答没有给出真实模型通过率或成本结论。
- 正式内容的建议转交范围为 `project.json`、`seed/`、`materials/`、`disclosure/`、`verification/`；`validation/` 的校准候选副本、早期 `environment/` 草案与本研究说明不应被当作新的用户任务或种子内容。正式环境从同任务 `environment-drafts/typer-py312/` 独立集成。
