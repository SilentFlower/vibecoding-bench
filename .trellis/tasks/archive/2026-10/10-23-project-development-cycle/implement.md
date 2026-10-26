# 完整开发周期实施计划

## 1. 开工边界

- 当前状态为 in_progress；最终 Brief 已完整展示并获用户“确认”，已启动任务并选择 inline 实施。
- 最新 PRD、设计与 Brief 已按顺序读取，用户批准后已运行 `task.py start`；实施和检查均选择 inline。用户新增页面动态配置直接归入 R10／AC14，没有重复整份 Brief 审批。
- 已有无关改动按任务创建时的基线保留；凭据和本地回执位于 Git 忽略的 `.deploy/project-development-cycle/`。

## 2. 先接一个 HTTP 调用

- [x] 阅读目标后端、数据库、错误处理与日志规范，确认当前 `ProjectScenarios`、`ProjectIterationManager`、创建 DTO 与 driver 的真实定义。
- [x] 新增小型 `orchestrator/project_dialogue.py`：配置读取、Chat Completions、动作 JSON 校验、有序多模型有限降级、脱敏异常与实际 usage。
- [x] 在 `orchestrator/main.py` 管理器初始化处注入客户端；配置仅传给 orchestrator，按需同步 `.env.example` 和 `deploy/v3/compose.yml`，保留这些文件原有无关改动。
- [x] 通过本地受控 HTTP 验证请求形状、主成功、402／429／暂时 5xx 降级、认证／参数错误、超时、无效 JSON 和主备均失败。禁止把真实服务余额耗尽当作测试手段。

## 3. 接入原任务循环和恢复

- [x] 增加外部请求的小型持久记录和唯一约束；保存有效结果再投递，迟到结果核对父状态／代次，密钥不入库。
- [x] 新完整周期的普通回复不创建评审，转为外部需求方的 reply／implement／verify；开发者后续执行恢复原 session、cwd 和现有文件。
- [x] 实施确认与最终交付分别核对；复用原生程序与必要最终审查，失败反馈包含可操作证据，支持对同一版本的有限异议复核。
- [x] 超时结束片段、原任务待续做；任务累计预算保留，普通交流／基础设施恢复不扣业务修复次数；同账号可恢复旧任务优先。
- [x] 覆盖五个中断点：外部结果生成未发送、发送未确认、消费未回复、交付未验证、验证未收口。消息、API 调用与接受结果均不能重复。
- [x] 修复真实观察到的局部 pasted_content 包装加后缀，只在原文可精确核对时接受；保留父链、来源及严格释放检查。

## 4. 一项需求和一个 BUG 先跑通

- [x] 内容 schema 3 复用当前真实场景结构，旧 schema 1／2 继续读取和原行为，新完整周期不受旧短题轮数限制。
- [x] 用 Click 错误附注增强与 Cachetools receiver 问题制作完整开发周期材料；每项有真实源码分析、细节追问、方案确认、实施、独立验证和必要返工。
- [x] 在隔离临时内容库和模拟模型下跑完整周期，核会话、文件、输入消费、预算和任务计数。
- [x] 页面及 API 展示完整任务、连续交流、待续做、交付与独立验收；区分外部需求方与 Claude 用量，显示实际降级模型。

## 5. 百项目重组与整体交付

- [x] 生成旧内容到完整需求／BUG 的逐仓映射和剩余清单；先复用 37 项真实修改和原研究中的有效工程目标，再归并纯问答材料。
- [x] 对有真实工程合同的 30 项目／36 任务补齐背景、材料、目标、授权范围与独立原生正反验收及回归。其余 70 项目逐仓记录缺少真实交付合同的阻塞，不计就绪，不以问答改名补数。
- [x] 内部小批逐批验证与对账，不为内容批次建立大量子任务；全部 100 项目保持在本任务范围内，阻塞项目不计就绪。
- [x] 最终校准实际项目／完整任务数量；核旧冻结版本与原账号、历史运行、会话、文件和权限保持。

## 6. 验证命令与证据

真实外部最小连通请求两次，加一次合成 JSON 动作／原会话交接请求；真实 Claude 调用为零。主备与多模型切换、业务循环、页面和 SQLite 已通过隔离替身验证；36 项内容的原版失败、参考通过和完整原生回归均通过。固定测试依赖已安装在忽略的 `.venv`，未修改系统环境。

基础准备（仅缺少依赖时）：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r orchestrator/requirements.txt -r orchestrator/requirements-test.txt
```

从 `orchestrator/` 运行受影响的回归；同时覆盖外部客户端、动态配置与任务循环：

```bash
../.venv/bin/python -m unittest test_project_dialogue test_project_requester_settings test_project_development test_project_scenario_content test_project_scenarios test_project_plans test_project_iterations test_project_evaluation test_project_review_runtime
```

从仓库根检查前端语法，并对每项实际内容运行原生验证器：

```bash
node --check webui/app.js
.venv/bin/python scripts/validate-project-scenarios.py --root <待验内容库> --project <实际项目键> --task <完整任务ID> --candidate <候选副本> --image <已核验账号镜像> --with-regression --expect passed
```

原版失败、错误候选拒绝分别使用实际候选路径和 `--expect failed`；验收材料覆盖问题语义，不以返回码替代业务结果。全量内容、来源、Git 字节、Docker 文件／执行位使用既有准入与交付工具逐仓核验，不把研究时基线当成当前验证。

隔离 Docker 与 UI／API／数据库对账复用 `deploy/v3/run_local_verification.py` 及 `verify_project_{scenarios,execution,browser,catalog,scheduling}.py`，新增外部 HTTP 模拟和完整周期场景。执行参数按实现后的真实 argparse 与隔离清单选取，不推测未定义 flag。

真实业务试点前展示候选范围、调用上限与环境，再取得适用授权；现有授权只覆盖指定外部主备的最小连通测试。模拟结果、真实外部接口、真实 Claude 任务和生产部署分别留证。

最终项目回归共 209 项，208 项通过、1 项因专用 nose2 环境缺失跳过；最终定向回归 25 项通过。36 项内容原生准入、双试点完整周期及真实 Chrome 配置操作均通过；完整周期中的开发者及语义评审回复为隔离替身，不作为真实 Claude 模型质量或缓存收益证据。回执分别位于忽略目录 `.deploy/project-development-cycle/` 下的 `project-tests-final.log`、`final-focused-tests.log`、`final-content-validation/summary.json`、`complete-cycle.json`。

## 7. 用户补充：页面动态配置

- [x] 读取现有运行时设置、管理桥与表单的真实定义；复用现有鉴权和零构建页面。
- [x] 一个 Base URL、私有密钥和有序多个模型动态保存；重启保留，前端不取回密钥；未覆盖时读取现有环境配置。
- [x] 客户端按多个模型有限降级；新配置对后续请求生效，旧模型从列表移除后不会卡住待生成消息；已生成消息继续复用。
- [x] API、模型调用、SQLite 任务归属及真实浏览器验证配置修改，确认无密钥回显，再重新进入 Check-All。

## 8. 检查与回退

- [x] 双试点先通过再扩内容；出现对话颗粒度、方案确认或续做偏差时先改试点，不把错误放大到百项目。
- [x] 改造后进入 `trellis-route(target=check)`／完整 Check-All；CHK 0、FBK 0，DOC 1 的过期说明已同步。`trellis-update-spec` 已将完整周期、动态模型配置、失败反馈及恢复边界固化到 `.trellis/spec/vibecoding-bench/backend/project-iterations.md`，结果 `written`，规范差异检查通过。
- [x] 用户已确认精确 Git 交付计划；175 个业务文件已提交并推送，保留其余 257 个已有改动。任务记录待部署验收后按同一计划提交。
- [x] 回退保留旧 release 与全部新旧任务现场，新模式作业停止后才能切旧服务，不为回退改写任务终态。

## Next Step

用户已确认精确提交计划并追加“并部署”。美国 v3 已更新为 `ci-39950873699-1`，停机备份及隔离恢复通过；66 个正式镜像源码、30 项目／36 任务目录、旧批次、17,003 个持久文件及 9 个无关容器均核对。真实 Chrome 的配置保存、空密钥沿用、刷新和双主题 390／1280 布局通过；服务容器只读查询能取得两个指定模型，真实生成请求为零。最终复核回执虽遇 SSH 中断，已从服务器读取确认成功，未重复执行。

上述上线回执位于忽略的 `.deploy/project-development-cycle/deployment/`，任务完成记录按已确认的精确范围随本次交付保存。后续真实 Claude 业务试点按独立范围处理。
