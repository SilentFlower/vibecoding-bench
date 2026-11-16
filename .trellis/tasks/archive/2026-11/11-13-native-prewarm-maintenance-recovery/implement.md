# 实施计划

1. 读取网关服务、平台更新、调度器运行时和 legacy-web 规范，复核类型及调用点。
2. 实现结构化后台准入，保持活动锁和未知状态拒绝准入。
3. 修正完成分类，增加平台维护等待项的一秒恢复检查，覆盖晚到回执。
4. 更新调度器投影与环境页说明。
5. 增加维护全周期、损坏门禁、真实失败退避、取消和队列限制回归。
6. 保存验证证据，进入 Check-All、Spec 及精确 Push 计划。

## 验证命令

- cargo fmt --check --manifest-path services/gateway/Cargo.toml
- cargo test --manifest-path services/gateway/Cargo.toml system_update
- 新增协调器聚焦测试，以及完整 cargo test --manifest-path services/gateway/Cargo.toml。
- python3 -m unittest discover -s services/orchestrator -p test_account_runtime.py
- python3 -m unittest discover -s services/orchestrator -p 'test_system_update_*.py'
- python3 deploy/flower2api/verify_environment_ui.py --output .deploy/environment-ui/native-maintenance

## 风险与回滚

重点检查门禁反复开关、回执晚到和真实失败退避。合成文件与本地 HTTP 验证沿原令牌和取消机制收口，回滚使用本任务精确 diff。

## FBK-001 修复验证

隔离协调器先由合成控制面返回 503，再进入维护并经过启动补偿；维护等待时准备 UUID 保持；维护开放后，调用次数在原冷却窗口内保持不变，状态恢复为原真实失败。显式账号变更清除冷却并正常恢复。无故障历史的一秒恢复、坏门禁和活动计数复用同一回归场景。

同一场景验证首次控制面迟到仍由原启动补偿恢复，维护后冷却账号归还队列位置，显式变更清除退避。
