# python-frontmatter 正式内容草案

本目录只供主会话审核与集成，不是正式发布库。使用当前 `orchestrator/project_scenario_content.py` 的真实 schema 2 格式；初稿阶段只做静态验证，随后目标镜像取证见末节，未调用模型。

## 内容与固定来源

- 上游：`https://github.com/eyeseast/python-frontmatter`，完整提交 `d2977d71638cb451bc06f2af3bb48e09e0dbe8c6`，MIT／Chris Amico。
- `seed/library/` 为现有固定检出的干净文件复制，包含 56 文件与许可证；无 `.git`、venv 或缓存。复制关系与逐文件 SHA-256 见 `verification/reference/source-files.json`；没有修改实际取证源码。
- `seed/app/` 仅有临时业务目录说明；本任务初始不把隐藏 TypeError 文档放入 seed。公开素材随各任务投放，`disclosure/` 只按入口或合法分支提供。
- `project.json` 定义 4 场景、6 稳定任务：FM-IN-01／02、FM-DG-01／02、FM-FX-01、FM-PL-01；没有人为代码依赖。独立场景使用独立原版工作区，问答不产生工程检查点。
- 默认 FM-S02 入口已选择诊断与随后显式修复请求；修复首问自带完整复现，不依赖诊断通过。`diagnose_only`、`unavailable`、`repair_only` 为同一场景的其他冻结入口，不能重复计任务。

## 公开和隐藏边界

`materials/` 是当前任务可见业务输入；`disclosure/` 保留按条件披露的最小复现、实际旧异常、用户澄清或收窄请求。`verification/` 的 rubric、观察器、预期与参考示例／补丁都留控制端，不进入候选。

FM-DG-01 的 `unavailable` 入口通过入口素材明确拿不到输入，只允许有依据的信息不足结果，不自动披露复现；正常入口必须材料补齐后完成诊断。评审需同时看入口、已披露事件和 criterion，不能只因回答说“资料不足”就通过。

## 受控原生草案

原生 JSON 使用主会话统一的 `script / args / python_paths / expected / resource_profile`；可选 `regression` 为冻结 cwd／argv。实际解释以主适配器实现为准。

- `consult.native.json`：读取控制端冻结回答，枚举最多 8 个可编译代码候选，并在各自全新业务目录运行；答复或 `app/example.py` 中只允许一个实际符合业务要求的完整程序。不是任意选第一个 fenced block。每次独立核对退出码、实际打印、输入字节、输出文件 metadata／正文；第二份隐藏业务周报验证不能硬编码原示例。
- `shallow.native.json`：直接核对原版浅覆盖、正文和 defaults 原对象保持，供无 BUG 结论提供真实行为依据。局部调用方合并示例的语义由 rubric 评审；本观察器尚未为任意表达的局部片段定义可靠的自动执行／结果提取契约，不能把此项原版事实观察夸大成“所有回答示例已实跑”。
- `repair.native.json`：11 项独立修复行为，包括两种保留键、组合往返、显式 handler 对象身份、公开构造、空头部／无头部、null、默认 content、文档覆盖默认值、路径／流读取及原 `to_dict()` 合同。脚本返回真实布尔或异常类型，由控制端对比 expected，不读候选自报测试结果。
- 修复的适用原生回归为完整 `pytest . --doctest-modules --doctest-glob README.md`，参考旧 56 主集合＋11 个严格 doctest 的 67 节点覆盖。原始节点集合保存在 `verification/reference/existing-native-coverage.json`，只是已有证据的副本，不是本轮结果。正式适配器须保护原集合，不能以候选删改 tests 后退出 0 冒充完整通过。

统一控制端路径为 `PROJECT_CANDIDATE_ROOT=/work/project`、`PROJECT_ANSWER_FILE=/request-data/answer.txt`。观察器也支持 `--candidate-root`／`--answer-file` 供主会话隔离校准；这些路径和回答文件不应写进候选工作区。原生脚本是独立文件，不读取相邻 rubric 或 reference，因此符合当前只复制一个受控 script 的执行方式。

## 参考修复与环境待办

`verification/reference/repair.patch` 只改变 `loads()`：先以正文和实际 handler 构造 `Post`，再更新 `post.metadata`。保留公开签名、浅 defaults、格式化及 `to_dict()`。该补丁已在后续隔离临时副本中校准，未应用到 seed 或实际取证源码。

`verification/reference/consult_example.py` 是供主会话校准观察器的完整咨询正例，不能投给候选。固定用例预期是内容作者待验证的合同，不是本轮运行日志。

`environment-profile.draft.json` 保留初稿时的依赖清单，资源为 null、artifacts 为空，故意不能通过 `validate_environment()`；后续已实测的 profile 位于本任务 `research/environment-drafts/python-frontmatter-py312/profile/profile.json`，由主会话审核后集成。咨询只需 PyYAML；完整严格回归还需旧环境中的 pytest、toml、pyaml 及真实依赖。

## 已做和未做

初稿生成时只执行 schema／JSON／AST 静态校验与源码复制摘要对账，其 `static-validation.json` 仍仅证明静态结构。随后已进行下述目标镜像环境和参考验收校准；未运行模型、未修改正式 catalog 或产品代码、未执行 Git 或部署。

主会话集成前须校准：原版在修复目标不通过、参考补丁通过独立行为与完整适用回归、咨询正例及错误／多代码歧义反例、所有合法披露入口、候选真实导入位置、只读文件范围和原生回归的冻结集合保护。

## 后续目标镜像校准

见 [离线环境与实测记录](../../environment-drafts/python-frontmatter-py312/README.md)。指定镜像 Python 3.12.15、无网络 UID1000、只读根、512 MiB／64 PID 下，原版完整 67 项及参考补丁后完整 67 项均实际通过，双方各有 11 个严格 doctest；原版修复目标预期不满足，参考补丁后 11 项独立行为全满足，原版中文周报业务／咨询参考程序及浅覆盖事实匹配冻结预期。所有结论有原始日志、XML、节点和资源记录，唯一取证容器已精确清理。

这补齐环境与参考校准证据，不能替代真实模型会话、分支调度、只读权限和回归保护机制的集成验证；咨询错误／歧义反例也没有在本次环境取证中自动宣称通过。
