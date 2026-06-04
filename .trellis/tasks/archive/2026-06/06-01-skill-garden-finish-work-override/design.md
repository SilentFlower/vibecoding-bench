# skill-garden finish-work override 注入设计

## 技术设计

### 目标仓库和范围

实施目标是 `/root/project/skill-garden`。该仓库是技能和 Trellis 增强包分发仓，不是完整 Trellis 工作区；任务记录继续保存在当前 `vibecoding-bench` 的 `.trellis/tasks/06-01-skill-garden-finish-work-override/`。

本任务只改 0.6 变体，目标路径限定为 `.trellis/0.6/overrides/` 及安装脚本中与 0.6 workflow override 注入相关的最小逻辑。0.5 / old 不纳入本次实现。

### 注入点

调整现有 `trellis-route` 注入模型：

- 在 0.6 中形成单个 `skill-garden overrides` 顶层 hub，注入到目标项目 `.trellis/workflow.md` 的 `## Phase Index` 顶部。
- hub 内分小节承载长文规则：routing gate、finish-work bookkeeping guard、push progress recovery / snapshot。
- `workflow-state:*` 内只放短机械规则，每个状态块只保留一个 skill-garden sentinel。
- 0.6 的短状态块模板放在 `.trellis/0.6/overrides/workflow-states/*.md`，不再硬编码在安装脚本里。
- 0.6 删除单独的 `.trellis/0.6/overrides/trellis-route.md`，routing 规则统一归入集中 hub，避免死模板和双入口。
- 安装脚本需要能清理旧的散块 sentinel（route enhancement、finish-work override、no-task-gate、push-progress-recovery、trellis-route、in-progress-push-snapshot 等），再写入新结构。

### Override 内容边界

finish-work override 应明确：

- `session_auto_commit` 只控制 `add_session.py` / `task.py archive` 这类脚本是否自动 stage/commit。
- 当目标项目 `.trellis/config.yaml` 设置 `session_auto_commit: false` 时，AI 不得声称 archive / journal 会自动生成 commit，也不得补做 bookkeeping commit。
- 收尾阶段可以运行 `task.py archive` 和 `add_session.py` 写磁盘记录，但必须把 `.trellis/tasks` / `.trellis/workspace` 的脏文件报告给用户。
- Phase 3.4 的代码工作提交仍然保留原工作流语义：仅在用户确认提交计划后执行。finish-work override 只限制 archive / journal 这类 bookkeeping commit。

### 状态块结构

目标结构如下：

- `[workflow-state:no_task]`：一个 `skill-garden workflow-state no_task v0.6` sentinel，合并 no-task guard 与 push progress recovery。
- `[workflow-state:planning]`：一个 `skill-garden workflow-state planning v0.6` sentinel。
- `[workflow-state:in_progress]`：一个 `skill-garden workflow-state in_progress v0.6` sentinel，合并 route gate 与 push snapshot。
- `[workflow-state:in_progress-inline]`：一个 `skill-garden workflow-state in_progress_inline v0.6` sentinel，保留 inline 场景下的 push snapshot 短规则。

这些状态块分别由 `overrides/workflow-states/no_task.md`、`planning.md`、`in_progress.md`、`in_progress-inline.md` 维护。安装脚本只负责读取文件、删除旧 sentinel、写入目标状态块顶部。

### 安装脚本兼容性

`scripts/install.sh` 目前在 3d 段内：

- 旧逻辑使用 `WF_ENHANCE="$GARDEN/.trellis/$TRELLIS_VARIANT/overrides/trellis-route.md"`。
- 用内嵌 Python 删除旧 sentinel 并插入新块。
- `should_install "workflow-enhancement"` 控制是否执行 workflow 注入。

设计上不引入新依赖，继续用内嵌 Python。0.6 使用 `overrides/workflow.md` + `overrides/workflow-states/*.md` 作为输入；0.5 / old fallback 继续读取各自原有 `overrides/trellis-route.md`。为了保持最小改动，优先在同一注入入口中完成：

- `workflow-enhancement` 代表安装 0.6 的完整 workflow override hub + 合并后的 state sentinels。
- `finish-work-enhancement` 可继续存在，但在 0.6 新结构下也应通过同一个 hub 更新 finish-work 小节，不能在 Phase Index 下再插入独立 finish-work 顶层块。
- 重复安装时先删除旧散块和旧 hub，再插入最新结构。

### 版本策略

- 只支持 0.6，因为用户明确要求“注意下是 0.6 版本里面的 override，不要改多了”。
- 0.5 / old 保持现状，不新增 finish-work override，也不改它们的安装内容。

### 风险与约束

- `/root/project/skill-garden` 已有未提交改动，实施时必须先读相关文件并只做局部补丁，不得覆盖整个文件。
- README 和 install.sh 当前也已脏，修改前后需要用 `git diff` 区分本任务新增内容。
- 注入文案必须足够高优先级，否则可能被目标项目后续 workflow 正文覆盖。

## 发布 / 回滚

- Rollout：通过 `bash scripts/install.sh --repo /root/project/skill-garden <target> workflow-enhancement` 或新增的精确增强名验证。
- Rollback：目标项目中删除 finish-work sentinel 块，或用 `.trellis/workflow.md.bak` 恢复；skill-garden 本身可用 git diff 精确回滚本次新增文件和脚本段。
