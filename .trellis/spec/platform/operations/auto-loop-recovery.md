> 来源专项：原 cc-runtime-bridge 仓库的多仓恢复工具规则。原工具位于该仓 `.trellis/scripts/project_repositories.py`。本规范供恢复原仓历史 run 时查阅；执行前应在来源仓核对工具和原始基线。来源提交见本任务 spec 映射。当前统一仓库沿根 Flower 工作流管理任务。

> 本文源码路径及命令以 `services/runtime/` 为工作目录。

# Auto loop 多仓恢复

## Scenario: 基于开工前证据补登关联仓库

### 1. Scope / Trigger

- 项目自有入口为 `.trellis/scripts/project_repositories.py`，用于 schema 2、commit-only、completed_with_blocked 的漏登记恢复。
- Flower 管理的 `auto_loop.py` 和 `git_evidence.py` 保持原所有权。恢复入口复用其加载、manifest 审计与状态写入函数。

### 2. Signatures

- `python3 .trellis/scripts/project_repositories.py --run-id <id> --baseline <文件> --baseline-sha256 <摘要> --repository <真实Git根> [--repository <真实Git根> ...] [--apply]`。
- `registrations(root, state, baseline, repositories) -> list[dict]` 仅生成预览记录。

### 3. Contracts

- 输入基线必须来自开工前保存的仓库 root/head/branch/status/files，调用时冻结整个文件的 SHA256。
- 仅补登基线已记录的真实仓库，HEAD 与分支保持原身份，索引为空且不存在冲突或未完成集成。旧 dirty 全部作为 protected-retained，逐文件核对摘要并拒绝链接与越界。
- 默认预览。`--apply` 在全部核验后，追加仓库、审计事件和 manifest revision，再调用原生状态写入器。队列、授权、任务阶段及 blocked 状态沿用原值。
- 补登后由原生 `retry-blocked --run-id <id> --all` 和 `next` 恢复。共享代码可采用一组已联合验证的多仓本地提交，分别关联已批准的任务；各任务仍独立记录完成与 Close。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 活动动作、待重绑决策或非终态 run | 失败关闭 |
| 基线摘要、旧文件内容、分支或 HEAD 漂移 | 失败关闭，保留原记录 |
| 未登记于旧基线、索引有内容、冲突或集成未完成 | 失败关闭 |
| 全部核验通过，未传 apply | 只返回预览 |
| 仓库已登记且证据仍匹配 | 幂等，无新写入 |

### 5. Scenarios and Examples

- 正常：主仓启动的 run 漏登记 bench 及其 cc2api 子仓。使用原始基线补登两仓，将旧343项 dirty 纳入保护，之后恢复原队列。
- 错误用法：用当前工作区重新生成“开工前基线”，或者直接改 runtime JSON。正确处理是复核原始证据，并通过此入口生成原生审计修订。

### 6. Tests Required

- `python3 -m unittest discover -s .trellis/scripts -p test_project_repositories.py`：旧文件保护、新代码归属、幂等、未知仓库、内容/HEAD/索引/集成漂移、路径越界、活动动作拒绝、只读预览、基线摘要及原生写入器边界。
