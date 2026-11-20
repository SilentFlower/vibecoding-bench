# 实施计划

## 前置状态

- 用户已确认完整 Brief，任务已进入 in_progress。
- 前置额度修复已完成：15 秒重置扫描、5 分钟同账号重试间隔、额度状态与真实零用量识别。
- 前置验证：854 项库测试通过、5 项跳过；86 项集成测试通过、4 项跳过；文档测试、cargo fmt、前端构建及合成页面状态验证通过。
- 前置全量 cargo 命令在集成阶段被终止，已用独立集成命令与文档测试补齐；日志位于 `/tmp/flower-quota-cargo-test.log`、`/tmp/flower-quota-integration.log`、`/tmp/flower-quota-doctest.log`。

## 顺序

1. [x] Brief 评审通过后 `task.py start`，进入 `trellis-route(target=implement)`。
2. [x] 按 `trellis-before-dev` 读取当前任务和相关 gateway/web 规范，保存当前差异基线。
3. [x] 新增设置默认与幂等补齐、原子解析、合法性校验；保留旧四项数组与冻结迁移定义。
4. [x] 实现重置窗口奖励，覆盖未来／到期／缺失／非法窗口和关闭回退。
5. [x] 复用完整成功诊断终态保存独立服务总耗时 EWMA，实现仅等待时启用的队列排序与缺样本回退。
6. [x] 扩展 API 可选摘要、设置草稿与详情展示；核对保存、取消、非法值和旧响应。
7. [x] 删除旧评分路径、旧设置与旧展示，将独立部署的选号复用统一智能选择器，保留容量统计。
8. [x] 补实际选号、并发／RPM／绑定回归，以及离线分组性能观测。
9. [x] 完成 `trellis-route(target=check)` 对应检查，处理本范围发现，再进入 Update-Spec 与精确 Push 计划。

## 验证

- `cd services/gateway && cargo fmt --check`
- 定向运行调度、设置解析／热更新、诊断总耗时采样和额度刷新用例。
- `cd services/gateway && cargo test --locked`；若工具会话限制终止长命令，按库测试、`--test '*'`、`--doc` 分段记录完整结果。
- 使用合成配置验证默认 0 与旧配置的等价选号、重置偏好改变选号、排队系数只影响等待候选、未知耗时回退和老会话稳定性。
- `npm --prefix apps/web run build`
- 使用合成管理接口验证设置保存／取消／错误定位、权重为 0、旧响应与调度因素，覆盖 1440／390px。
- 本地微基准覆盖 1／8／32／64 组、1／10／100 候选；保存 CPU／构建模式、测量轮次与每轮耗时，不调用真实模型。
- `git diff --check`，逐文件核对本任务与原有 dirty 变更。

## 风险与回退点

- 耗时 EWMA 是等待估计，实际许可沿用原闸门；缺样本显式回退。
- 分组表保持每账号 64 组上限，统计更新不跨 await 持有同步锁。
- 权重存储失败或校验失败保留旧原子快照。
- 回退两个主权重至 0 即恢复原排序；提交范围包含前置修复及本任务改动，其他 dirty 变更保持原归属。

## 已确认的增量

用户追加删除旧评分系统，纳入当前任务；原有四项智能权重与新增偏好继续实施，补充历史配置退出生效范围及独立部署回归。

## 当前验证证据

- `cargo test --locked scheduling_preferences`：4 项库用例、1 项集成用例通过。
- `cargo test --locked`：854 项库用例、87 项集成用例通过；文档测试通过。6 项库用例和4项环境用例在默认命令中跳过。
- 显式微基准通过，补齐默认跳过的性能用例；实际环境跳过共9项。12组测量详见 verification/group-performance.md。
- `npm --prefix apps/web run build` 与 `python3 deploy/flower2api/verify_scheduling_preferences.py` 通过，覆盖保存／撤销／精度／失败草稿／旧评分移除／等待回退／旧响应／1440和390px。

- Check-All full 通过，CHK／FBK／DOC 均为 0；已同步 3 份项目规范。
- 为隔离同文件中的其他任务修改，生成 19 文件独立补丁并应用到当前 HEAD 的临时源码快照；独立快照的前端构建与 `cargo check --locked --tests` 均通过。
