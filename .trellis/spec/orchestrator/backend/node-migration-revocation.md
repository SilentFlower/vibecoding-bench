# 迁移目标撤销与重试

## 1. Scope / Trigger

用于 CC 和 AGY 在中央归属提交前撤销目标，以及后续新操作准备或撤销时核对既有停止副本。中央归属和停机阶段见 [人工节点集群、所属执行与停机迁移](./account-runtime-v3.md#scenario-人工节点集群所属执行与停机迁移)。

## 2. Signatures

- 共用 `NodeExecution._previous_copy(root: Path, intent: dict) -> tuple[dict, list]`，输入意图中的操作、节点、账号、环境与目标 revision 为本次已校验范围。
- `node-migrations/<旧操作>/revoked.json` 是协议 1 的目标撤销收据。字段为 `operation_id, node_key, account_id, environment_id, revision, phase`，阶段固定为 `revoked`。

## 3. Contracts

- 目标原副本须有 `node-fence.json`，其版本为正整数且小于或等于新目标版本。原 fence 必须属于不同操作，并精确匹配当前节点、账号和环境。
- 版本相同时，原操作撤销收据须存在且所有字段精确匹配。远程节点的 `node-assignment.json` 还须证明同一原操作处于 `fenced`。实际角色继续核对 ID、部署、环境、角色类型及 `Running=false/Pid=0`。
- 新准备把核对后的旧资料保存在本次 `previous-environment`。已撤销操作继续依据其原墓碑拒绝迟到上传和发布。

## 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 同版本且原撤销收据、fence、归属、实际角色全部匹配 | 可以继续新准备，或取消本次尚未发布的操作 |
| 同版本撤销收据缺失或字段错配 | 返回受控的「目标同版本副本缺少匹配的原撤销收据」 |
| 原操作、账号、环境、停止证明或实际角色存在冲突 | 拒绝接管，保留现场 |

## 5. Scenarios and Examples

- 中央源 revision 1 迁往目标 revision 2。中央提交前取消并确认目标已停止。新的操作仍可使用目标 revision 2，实际环境代次递增。
- 目标版本相同且只有停止容器。须获取同一原操作的撤销收据后才能接管。

## 6. Tests Required

- `test_cancelled_cc_target_can_be_prepared_again_at_the_same_revision` 调用真实准备与撤销入口，验证下一笔撤销、新准备、旧资料和代次。测试同时断言缺失或错配撤销收据、仍有实际运行角色和迟到旧发布均被拒绝。
