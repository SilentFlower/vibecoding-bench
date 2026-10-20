# 当前能力与规划约束

## 已核对的代码事实

- `orchestrator/main.py:9978` 的 `TaskIn` 以 `topic_no`、`account_id` 为必填项；`prompt_mode` 当前控制题库需求表达，不是项目运行模式。
- `orchestrator/main.py:9998` 的 `BatchIn` 以 `topic_ids` 批量创建任务，不能仅改提示词就建立独立的长期项目语义。
- `orchestrator/account_runtime.py:1560` 的 `_project_view` 根据环境 ID 和 run ID 派生物理项目别名。普通新 run 不会自然复用另一个 run 的项目目录。
- `orchestrator/account_runtime.py:1643` 的 `run_session_path` 解析原 run 对应的主会话目录。
- `orchestrator/account_runtime.py:2005` 的 `begin_continue` 可以在原工作目录领取续聊，并保持原账号的执行约束。
- `orchestrator/main.py:10960` 的 `/api/runs/{rid}/continue/start` 已支持对结束的 run 建立终端续聊；会检查账号可用性和运行窗口。
- `.trellis/spec/vibecoding-bench/backend/topic-prompt-contract.md` 要求原有 topic prompt、冻结补充计划和历史运行保持一致性。新模式不应复用 `natural/canonical` 的名字来改变其含义。

## 已收敛的设计边界

- 用户已确认全自动运行、相同项目跨账号或批次使用相同基线，以及 100 个项目、每项目至少 20 步的规模。
- 首版预置内容库，任意 Git 导入与既有 run 转项目不纳入本轮；具体实例与运行归属、验收和恢复方案见 `../design.md`。
- 项目库属于控制端；账号可见工作目录只在首次实际启动时建立，之后持续保留。
- 当前 v3 的窗口／额度相关代码存在并行任务的工作区改动；后续实现必须以实际最新代码为准，保留其他工作。

## 对改进目标的限制

- 可评价指标是明确的功能改进、验收结果和每轮实际用量，不能把“看起来像真实使用”作为验收依据。
- 原有封禁排查未形成因果结论。真实项目迭代是产品与工作负载设计选择，不构成避免平台封禁的保证。
- 官方建议明确上下文、限定任务范围并提供可执行的验证依据：[Claude Code 最佳实践](https://code.claude.com/docs/en/best-practices)。已有项目也可能因上下文读取而增加输入成本：[成本管理](https://code.claude.com/docs/en/costs)。
