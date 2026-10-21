# 首批三项目内容包实施计划

## 开始条件

本任务已完整展示 Brief 并获得用户确认，随后通过 `task.py start` 进入 in_progress，沿用 `trellis-route(target=implement)` 的当前会话模式。下列勾选均有实际证据，本地实现、验证和检查已完成；精确 Git 计划已获确认，业务内容已推送，最终任务进度见 `task.json`。

主代理串行处理共享文件和集成；如果路由选择子代理，则按下述明确所有权派发，告知各实现者不是唯一协作者，不回退已有变更。每次写代码前读取 before-dev 与相关已有类／方法。

## 1. 固定来源与准入环境

- [x] 记录实现前当前 catalog、三个已接入项目和环境的完整文件清单／SHA；保留已有 277 个计划外未提交文件。
- [x] 取得当前正式 account 镜像并校验 RepoDigest、Python 精确版本、平台；不混同镜像配置与 registry digest。
- [x] 分仓导出固定 Git 对象、许可和原生测试，排除临时环境／日志；记录上游完整文件清单与被忽略同名文件。
- [x] 冻结实际测试依赖、wheel 与 SHA，分别预备三套离线 profile；通过实际候选导入和正常原生 smoke，记录资源和清理。

## 2. 可信回归最小扩展

- [x] 主代理所有权：`orchestrator/project_native_regression.py` 及必要的定向回归测试。添加三 suite 和 Jinja src 布局，以旧默认兼容；不改变 Scheduler、schema、DTO 或账号模块。
- [x] 测试真实 src 布局导入、错导入 site-packages 拒绝、候选删除原测试仍使用冻结集合、控制文件／hook 变更拒绝及旧 suite 默认。
- [x] 在目标 account 镜像对各原版完整适用集合重新校准节点合同；记录命令、解释器／插件、节点、结果与 skip 原因。历史 228／911／81 不是本轮通过结果。
- [x] 将可信回归脚本冻结到新增内容的 verification，验证副本与可信实现 SHA 一致；旧三仓副本和合同不改。

## 3. 三项目内容并行制作

- [x] TinyDB 所有权：`project_library/projects/tinydb/`、`project_library/environments/tinydb-py312/`、本任务对应研究／验证证据。按母任务 data-candidates 的四场景十二项生成实际 manifest、英文物料、私有 rubric/native。
- [x] Jinja 所有权：`project_library/projects/jinja/`、`project_library/environments/jinja-py312/` 和对应证据。四场景十二项，明确 src 导入、两个修改同场景 code 父链、异步过滤器正反例与无需改代码路径。
- [x] schedule 所有权：`project_library/projects/schedule/`、`project_library/environments/schedule-py312/` 和对应证据。五场景十三项，两个修改各自独立场景，业务假时钟不能控制平台 driver。
- [x] 每仓制作只在控制端保存的参考候选／答案，先实测两工程目标原版失败、参考通过和兼容反例；非修改任务逐项区分可执行答复和语义事实。
- [x] 正常缺材料披露、材料无法提供和直接修改入口按真实任务 ID／依赖校验；禁止跨场景 requires，入口不能漏掉 code 前置。
- [x] 冻结无材料入口的明确业务记录，实际检查候选与评审消费内容；native 不依赖不存在的 entry 入参，通用证据不泄露正常路径私有复现。

## 4. 统一集成与字节保真

- [x] 主代理所有权：`project_library/catalog.json`、`project_library/README.md`、`.gitattributes` 的精确任务路径规则，以及确需的语言／公开投影测试。只有上游真实同名文件需要时才改精确 `.gitignore` 例外。
- [x] 生成新 version 和真实 digest，实际静态加载六项目／二十六场景／五十七任务；原三仓及其环境的文件全集／SHA 保持一致。
- [x] 逐项核英文指令、私有 rubric／分支／材料说明，核中文公开标题／目标／路线，原始业务字面和源码不翻译。
- [x] 独立临时 Git 导出／Docker 构建上下文核文件全集、字节、版本和 digest；不修改用户索引，不用工作区校验代替导出校验。
- [x] 运行新旧 install／历史读取回归；通过之前不宣称内容已经就绪。

## 5. 原生与模拟验收

- [x] 所有具备 native 的新增任务按正常／必要反例实际执行；六工程参考候选逐项业务通过并跑当前冻结完整上游回归，Jinja M02 再验 M01 能力。
- [x] 专用内部网络、空 SQLite、合成账号、mock CLI 执行三十七默认任务，记录每任务实际候选／评审及 business result；同任务材料补充和恢复不增加独立任务数。
- [x] 覆盖改变实际物料或合法结论的非默认入口／披露，验证无材料结论不被当作未完成；涉及问答检查点为零，Jinja code 依赖只接受前置已通过摘要。
- [x] 页面/API/SQLite 交叉核对六项目目录、分类结果、尝试、剩余预算、用量覆盖及成果；桌面和 390px，明暗主题；当前 catalog 失败仍读历史。
- [x] 保留失败原因和原始证据，核仅清理本次随机测试标签资源，无真实模型／OAuth／生产操作。

## 6. 检查与收口

- [x] 通过 `trellis-route(target=check)` 进入 inline/full Check-All；未发现 CHK／FBK，过期事实记录按 DOC 通道同步。不将 mock 语义质量标为真实通过。
- [x] 按既有 Update-Spec 流程同步被本轮证据改变的准入规范；只修改 `project-iterations.md` 的相关契约，源码反查与差异检查通过，未重写旧一百仓研究文件。
- [x] 输出本地就绪内容数、native 通过、模拟机制和未验证边界，交付报告见 `research/integration-report.md`；实际 Git／发布以收敛后的精确计划为准，不自动复用旧修复发布授权。

## 验证命令与证据位置

已有入口可直接复用，参数中的任务、镜像和输出必须来自本轮实际冻结对象：

```bash
python3 scripts/validate-project-library.py --root project_library
python3 scripts/validate-project-scenarios.py --root project_library --project <项目key> --task <任务ID> --image <固定账号镜像> --output <本轮结果.json>
python3 scripts/validate-project-scenarios.py --root project_library --project <项目key> --task <工程任务ID> --candidate <私有参考候选根> --image <固定账号镜像> --with-regression --output <本轮结果.json>
PYTHONPATH=orchestrator .deploy/project-iteration-repairs/venv/bin/python -m unittest test_project_native_regression test_project_scenario_content test_project_native_verifier test_project_evaluation test_project_scenarios
```

共享回归扩展的定向测试类为 `test_project_native_regression.NativeRegressionTests`，六项测试连同上述内容／验收／评测／场景测试共四十七项通过，日志为 `.deploy/project-catalog-pilot-pack/focused-tests.log`。整包模拟复用既有 `.deploy/mock-scenario-pilot-20261021/` 的真实调度方法，在全新 `.deploy/project-catalog-pilot-pack/` 内保存独立输入、原始日志和清理证据，未覆盖旧试跑结果。新内容的默认任务数由新 manifest 实际加载，不复用旧“20项”固定断言。

可审查的命令、摘要和结果写本任务 `research/`，大型原始资料留忽略目录并在研究中指向实际路径。已通过的昂贵检查不重复跑，只有新改动、失败或证据漂移才重验相关范围。

## 停止与回滚边界

来源、许可、候选导入或完整回归合同不成立时只暂停相应内容准入，保存证据后修正；不能裁剪成空壳或假包补足数量。出现产品协议之外的新能力需求，先同步三件套再评估增量范围。本轮没有生产回滚动作；旧发布、数据库、账号和历史成果不动。首批未完整通过之前不能把母任务的十项目或 150～200 任务目标标为完成。
