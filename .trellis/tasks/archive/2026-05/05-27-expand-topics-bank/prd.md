# brainstorm: 扩充 topics 题库与优化提示词

## Goal

扩充并重写 `topics` 题库，让题目更适合作为 vibecoding-bench 的批量评测输入：题量更充足，难度分布更有区分度，题目描述从一句话提示升级为可执行、可验收、对 AI 编程能力有真实拉扯的项目 brief。

## Background / Known Context

- 用户反馈当前 topics 题库量太少，部分题目太简单，某些默认提示词也太简单。
- 用户希望继续扩充题库，并补充完善原有 100 条描述。
- 用户确认本次目标题库规模为 200 条。
- 本地 `topics.md` 当前共有 100 条，编号 1-100，按 10 个分类组织。
- 后端 `orchestrator/main.py` 中 `topics.md` 只作为首次 seed 来源；`topics` 表一旦有数据，服务后续以 SQLite 为主，不会自动把 `topics.md` 的改动同步到已有数据库。
- 当前默认 prompt 由 `build_topic_prompt(topic)` 生成，只拼接标题、描述和一段通用 MVP 指令。
- 远程服务器部署目录为 `/root/vibecoding-bench`，当前不是 git 仓库；远程 `topics.md` 也是 100 条，编号 1-100。
- 远程容器运行镜像 `huajiwuyan/vibebench-orchestrator:20847f8`，宿主端口 8080。
- 远程 `data/db.sqlite` 已有 `topics` 表，API 登录后 `/api/topics` 返回 100 条，编号 1-100。
- 因远程数据库已 seed，单独替换远程 `topics.md` 不会改变当前 WebUI 看到的题库；上线需要同步 SQLite 题库，或提供一次性导入/重置流程。

## Assumptions (temporary)

- 本任务优先改造题库内容与默认 prompt 质量，不改变现有账号、任务、运行调度主流程。
- 原有 100 条的编号保留，新增题目从 101 开始连续编号，最终形成 1-200。
- 题目描述需要保持 Markdown seed 解析兼容：每条仍使用 `- [ ] N. **标题**：描述` 的单行格式，除非另行决定修改解析器。
- 远程上线需要覆盖已有 SQLite 题库，而不只是提交 `topics.md`。
- 本次不新增 topic 字段，不改 `topics` 表结构；继续使用现有 `no/title/description/category/enabled` 数据模型。

## Open Questions

- 远程同步执行时间点需要在实现完成后确认：本任务可提供同步步骤，是否立即执行由用户最终确认。

## Requirements

- 扩充 `topics.md` 题库到 200 条，新增题目必须覆盖比当前更丰富的项目类型和技术挑战。
- 完善原有 100 条描述，减少“只有功能名 + 简短特性”的题目，补足核心用户场景、关键功能和验收方向。
- 提高题目整体难度梯度，避免大量题目只能产出非常简单的 Todo / CRUD / 静态页面。
- 不新增难度、标签、验收项等结构化字段；必要信息写入现有描述字段。
- 默认 prompt 需要更明确地要求 AI 产出可运行 MVP、说明启动方式、列出验证方式，并对不确定项作合理假设。
- 保持题库在 WebUI 中可读，不把过长说明塞到卡片上导致浏览体验明显变差。
- 需要考虑远程服务器已有 SQLite 题库的同步路径，确保上线后远程 WebUI 实际看到新题库。
- 所有用户可见文案、注释和文档使用中文。

## Acceptance Criteria

- [ ] `topics.md` 的题目数量达到 200 条，编号 1-200 连续且无重复。
- [ ] 原有 1-100 条均已补充为更完整的项目描述，不再只有过短提示。
- [ ] 新增题目有明确分类，整体覆盖 CLI、Web、AI、数据、自动化、协作、工程工具等多种能力维度。
- [ ] 默认 topic prompt 比当前通用指令更具体，能引导 Claude Code 说明启动、验证和实现范围。
- [ ] 本地解析函数能正确解析全部题目，解析数量与文档统计一致。
- [ ] 远程已有 SQLite 题库有明确同步方案，并经过只读或可回滚验证。
- [ ] 不破坏现有 topics CRUD、批量任务创建和 runs 流程。

## Definition of Done

- 规划文档与实现计划完成并通过用户确认。
- 代码或数据改动通过本项目约定的质量检查。
- 本地题库解析验证通过。
- 如执行远程同步，先备份远程 `data/db.sqlite`，再同步并验证 `/api/topics` 返回目标数量。

## Out of Scope

- 不在本任务内实现完整自动评测系统或 LLM-as-judge。
- 不在本任务内重做 WebUI 信息架构，除非新增字段迫使 UI 必须调整。
- 不在本任务内删除历史任务、运行记录或远程 workspace/flows 数据。

## Research References

- 远程部署规范：`.trellis/spec/deploy/remote-deploy.md`
- 后端 topics seed 与 prompt 逻辑：`orchestrator/main.py`
- 当前 seed 文件：`topics.md`
