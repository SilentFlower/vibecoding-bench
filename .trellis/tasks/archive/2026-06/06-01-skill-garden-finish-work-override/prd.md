# skill-garden finish-work override 注入

## 目标

在 `/root/project/skill-garden` 中新增一套 Trellis `finish-work` override 注入能力，让安装到目标项目后的 Trellis 收尾流程能明确区分“脚本自动提交”和“AI 按流程手动提交”，避免 `session_auto_commit: false` 时仍被 workflow / skill / command 文案诱导产生 archive / journal 提交。

## 背景 / 已知上下文

- 用户已确认要创建 Trellis task，并希望在 `/root/project/skill-garden` 里做注入，对 `finish-work` 做一定 override。
- 用户已进一步收窄范围：只做 0.6 版本里的 override，不要改多了；因此本任务不改 0.5 / old 变体。
- 用户确认新的整理方向：`workflow-state:*` 内不再分散多次注入；每个状态块只保留一个 skill-garden sentinel。完整解释集中到 `## Phase Index` 下的 skill-garden override hub。
- 前置排查结论：目标项目的 `.trellis/config.yaml` 中 `session_auto_commit: false` 被脚本正确读取；`add_session.py` 和 `task.py archive` 在该配置下会跳过 git stage/commit。
- 实际“总是自己 commit”的来源更可能是流程提示：`.trellis/workflow.md` Phase 3.4 要求 AI 驱动 commit，`trellis-finish-work` / Claude command 文案也仍写着 archive / journal 会产生 commit。
- `/root/project/skill-garden` 不是完整 Trellis 工作区：它没有 `.trellis/scripts/` 和 `.trellis/tasks/`，只有版本化增强包；因此本 task 记录在当前 `vibecoding-bench` Trellis 任务系统中，实施目标仓库是 `/root/project/skill-garden`。
- `/root/project/skill-garden` 当前已有用户或其他会话留下的脏文件：`trellis-route` 相关 override / skill、`README.md`、`scripts/install.sh`。实现时不得回滚或覆盖无关改动。
- `skill-garden` 当前已有 `trellis-route` override 注入机制：`.trellis/<variant>/overrides/trellis-route.md` 作为模板，经 `scripts/install.sh` 注入目标项目 `.trellis/workflow.md` 的 `## Phase Index` 顶部，并写入 workflow-state guard。0.6 本次改造后不再保留单独 `trellis-route.md`，routing 长文归入 `overrides/workflow.md`。

## 需求

- 只在 `skill-garden` 的 0.6 变体中新增并整理 workflow override 注入能力，覆盖 Trellis 收尾阶段对 archive / journal commit 的误导性描述，同时收敛状态块 sentinel 结构。
- Override 必须高优先级、幂等、可重复安装，不能依赖手工删除旧块。
- `## Phase Index` 下必须形成一个集中式 `skill-garden overrides` hub，包含 routing、finish-work bookkeeping、push progress / snapshot 等长文规则。
- 0.6 的状态块短规则必须放在 `overrides/workflow-states/*.md`，安装脚本只做读取、清理和注入。
- `workflow-state:*` 内每个状态最多保留一个 skill-garden sentinel：
  - `no_task` 合并 no-task gate + push progress recovery。
  - `planning` 保持 planning handoff guard。
  - `in_progress` 合并 route gate + push snapshot。
  - `in_progress-inline` 保持 push snapshot 或 inline 相关短规则，不能继续新增多个散块。
- Override 必须让 agent 在 `session_auto_commit: false` 时：
  - 不把 `task.py archive` / `add_session.py` 视为会自动 commit 的操作；
  - 不主动创建 `chore(task): archive ...` 或 `chore: record journal` 这类 bookkeeping commit；
  - 只报告已写入磁盘的 `.trellis/tasks` / `.trellis/workspace` 脏文件，交由用户手动处理；
  - 仍允许真正的代码工作提交遵循 Phase 3.4 的用户确认流程。
- Override 只限制 archive / journal 这类 bookkeeping commit，不禁止 Phase 3.4 中经用户确认的代码工作提交。
- Override 只面向 Trellis `0.6` 变体，不同步 `0.5` 和 `old`。
- 安装入口应保持与现有 `workflow-enhancement` 机制一致：默认安装 trellis 包时可注入，也能通过指定增强名单独重灌。
- README 需要更新，说明新增 finish-work override 的作用、安装方式、回滚方式。

## 验收标准

- [x] `skill-garden/.trellis/0.6/overrides/` 中存在集中式 workflow override hub，内容明确约束 routing、finish-work bookkeeping、push progress / snapshot 行为。
- [x] 0.6 状态块短规则位于 `overrides/workflow-states/*.md`，不再硬编码在安装脚本里。
- [x] 0.6 不再保留单独的 `overrides/trellis-route.md` 死模板。
- [x] 安装后的 `.trellis/workflow.md` 在 `## Phase Index` 下只出现一个 skill-garden 顶层 override hub。
- [x] 安装后的 `workflow-state:in_progress` 中只出现一个 skill-garden sentinel，且同时覆盖 route gate 与 push snapshot。
- [x] 安装后的 `workflow-state:no_task` 中只出现一个 skill-garden sentinel，且同时覆盖 no-task gate 与 push progress recovery。
- [x] 安装后的 `workflow-state:planning` 中只出现一个 skill-garden sentinel。
- [x] 不新增或修改 `.trellis/0.5/`、`.trellis/old/` 下的 finish-work override。
- [x] `scripts/install.sh` 能把该 override 幂等注入目标项目 `.trellis/workflow.md`，重复执行不会产生重复块。
- [x] 指定 `workflow-enhancement` 或新的增强名时，能只重灌相关 workflow override，不强制重装所有 skill。
- [x] `README.md` 记录新增 override 的用途、安装/重灌命令和回滚方式。
- [x] 验证在临时目标项目上执行安装后，`.trellis/workflow.md` 包含 finish-work guard，且重复安装 diff 稳定。
- [x] 不回滚 `/root/project/skill-garden` 中既有未提交改动；最终变更清单能区分本 task 改动与原有脏文件。

## 已确认决策

- finish-work override 只覆盖 `session_auto_commit: false` 造成的 archive / journal bookkeeping commit 误导；Phase 3.4 的代码工作提交保持原流程。
- workflow override 结构采用“Phase Index 集中 hub + 每个 workflow-state 一个短 sentinel”的形态，后续新增规则不再向同一状态块追加多个 sentinel。
- 0.6 删除单独 `overrides/trellis-route.md`，避免留下不再生效的分散模板；状态块短 sentinel 通过 `overrides/workflow-states/*.md` 独立维护。

## 完成定义

- 任务规划已覆盖 `prd.md`、`design.md`、`implement.md`。
- 实现改动限制在 `skill-garden` 的 override 模板、安装脚本和 README 等必要文件。
- 用临时目录验证安装注入与幂等性。
- 结束前明确列出未提交文件来源，避免混入已有脏改动。

## 非目标

- 修改 Trellis 上游源码或全局 npm 安装目录。
- 修改 `skill-garden` 的 0.5 / old 变体。
- 回滚或重写已有 `trellis-route` 注入逻辑，除非为接入 0.6 finish-work override 必须做最小扩展。
- 自动提交 `/root/project/skill-garden` 的现有脏文件。
