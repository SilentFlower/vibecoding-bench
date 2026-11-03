# 实施与验证

- [x] 收敛PRD并展示Brief，按既有免确认授权启动，route选择inline。
- [x] 实现共享参数构造、首输出观察与新增可选诊断字段，保留响应头与历史兼容。
- [x] 实现冻结的延迟分组及成功反馈，隔离模型/思考/stream并限制分组数量；保持健康、准入与发送策略。
- [x] 修复账号表单增量提交及服务端普通配置按列更新，验证活动请求/CLI期间热更新和并发缩容、RPM唤醒；凭据/身份保护保留。
- [x] 更新Settings和调度详情文案，标明首输出和账号汇总，不增加不必要页面。
- [x] 定向测试、完整cargo test -- --test-threads=4、cargo fmt --check、npm run build、git diff --check；复用有效结果，不重复扩围。
- [x] 完成Pre-Check、Check-All、最小Spec更新，精确提交cc2api再父仓gitlink/Spec并推送；核验自动GC ahead归属。
- [ ] 获取本次CI联合镜像清单，按US生产SOP部署；当前数据/身份、非目标容器和配置保持，只重建同部署服务与账号角色。
- [ ] 页面200/管理未登录401/数据库quick_check与新代码、同批镜像验收，执行定向镜像回收并核对磁盘；记录无真实模型探针。
- [ ] 真实交付完成后task_progress --complete与Close，精确提交并推送任务记录。

## 停止与恢复点

任何凭据/身份/归属不一致停止相应生产步骤，不用历史RT覆盖；部署或清理失败保留已完成事实。代码修复不扩展到RSS或旧版恢复。

## 验证与审查证据

- cc2api：`cargo test --locked -- --test-threads=4` 完整通过，823通过、4个既有外部条件测试忽略；新增首输出与热更新用例均通过。
- 队列最后一处调整只避免对已同步目标重复调整；随后 `cargo test --locked --lib hot_ -- --test-threads=4` 在最终源码上13通过，覆盖旧快照、活动API/CLI、缩容排队、取消与再次扩容。
- 独立临时PostgreSQL数据库运行 `account_store_timestamp_test::usage_limits_postgres_storage_and_legacy_migration --ignored`，1通过；临时库已删除。发现并修复同一管理入口套餐可空字段的预编译参数类型漂移，新增选列更新同样固定文本绑定。
- web：`node --experimental-strip-types --test tests/accountUpdate.test.mjs`，2通过；`npm run build`通过。
- `cargo fmt --package claude-code-gateway -- --check`、父/子仓 `git diff --check`通过。
- Check-All full：三维通过，CHK/FBK均0；上线后版本、鉴权、数据库、身份与其他容器检查由本次部署执行者继续。Spec更新只改backend/service-architecture.md，核对实现与差异检查通过。
- 自动GC历史91908eee已由verify_gc_commit验证；原有vibecoding-bench 334、ai-fund 14个dirty文件散列保持。
