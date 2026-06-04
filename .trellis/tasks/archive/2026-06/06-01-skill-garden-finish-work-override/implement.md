# skill-garden finish-work override 注入实施计划

## 实施清单

- [x] 读取 `/root/project/skill-garden` 相关文件的当前 diff，标记既有改动与本任务将触碰的区域。
- [x] 将 0.6 override 模板整理为 Phase Index 集中 hub，内容覆盖 routing、finish-work bookkeeping、push progress / snapshot。
- [x] 删除 0.6 独立 `overrides/trellis-route.md`，避免保留不再生效的分散模板。
- [x] 将 0.6 `workflow-state:*` 短 sentinel 外置到 `overrides/workflow-states/*.md`。
- [x] 不修改 `.trellis/0.5/` 和 `.trellis/old/`。
- [x] 修改 `scripts/install.sh` 中 0.6 workflow 注入相关逻辑，支持 hub 和合并 state sentinel 的幂等删除与插入。
- [x] 最小更新 `README.md`，说明 0.6 workflow override hub、状态块合并策略和重灌命令。
- [x] 用临时目标目录验证安装注入：
  - [x] 首次安装能写入一个 skill-garden hub。
  - [x] 重复安装不产生重复块。
  - [x] `workflow-state:in_progress` 只有一个 skill-garden sentinel，且包含 route + push snapshot。
  - [x] `workflow-state:no_task` 只有一个 skill-garden sentinel，且包含 no-task + push progress recovery。
  - [x] 0.5 目标不注入 0.6 hub / finish-work 规则。
- [x] 检查 `git diff`，确认没有回滚或误改已有 `trellis-route` 相关内容。

## 验证

- `bash -n scripts/install.sh` 已通过。
- `/root/project/skill-garden`: `git diff --check` 已通过。
- `/root/project/vibecoding-bench`: `git diff --check` 已通过。
- 用临时 snapshot repo 验证 0.6 `workflow-enhancement`: hub=1，四个新状态 sentinel 各 1，旧 route / finish-work / push 散块均为 0。
- 用新版临时 snapshot repo 验证：0.6 `overrides/trellis-route.md` 不存在，`overrides/workflow-states/*.md` 为 4 个文件。
- 从旧散块 workflow 迁移验证通过：hub=1，四个新状态 sentinel 各 1，旧 top-level route / finish-work / push 状态散块均为 0。
- 重复执行 0.6 `workflow-enhancement` 后输出“已是最新”，计数不变。
- 0.6 `finish-work-enhancement` 作为集中 hub alias 验证通过。
- 0.5 `workflow-enhancement` 验证未注入 0.6 hub / finish-work 规则。
- 已把新结构安装到 `/root/project/vibecoding-bench`，`.trellis/workflow.md` 中 hub=1，四个新状态 sentinel 各 1，旧散块均为 0。

## 评审门禁

- finish-work override 范围已确认：只限制 archive / journal bookkeeping commit，不禁止 Phase 3.4 代码工作提交。
- 实现后在提交计划中单独列出 `/root/project/skill-garden` 原有脏文件，避免混入非本任务改动。
