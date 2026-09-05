# Brief — 发布并验证 cc2api Claude Code 2.1.260

## Goal

- 在抓包证据和 cc2api 协议适配已完成、提交并推送的基础上，发布生产 cc2api，验证
  2.1.260 默认画像、条件迁移和真实请求，并完成与已部署 bench 2.1.260 的一致性及
  2.1.257 回滚材料保留及未演练说明。

## Scope

- 发布前记录 cc2api 与 bench 的旧镜像、连接和活跃任务状态、运行配置、数据库备份、
  profile/range、账号 canonical env 及管理员自定义设置的脱敏摘要。
- 核对 cc2api 精确 SHA tag、`latest` 和镜像 digest 一致，在低连接窗口 pull 并 force
  recreate `claude-code-gateway`。
- 部署后验证容器和 HTTP、镜像 digest、数据库完整性、默认 profile/range、账号版本
  分布、自定义设置保留、bootstrap/hello 以及协议和迁移错误日志。
- 复用已有协议、部署和用户实际使用证据，核对 bench 默认版本、run 版本快照及已完成
  的 continue 回归记录；不追加模型或生产 continue 测试。
- 保留已确认的旧 cc2api 镜像、两套数据库备份、联合回滚顺序与恢复边界；完整演练
  未执行，按用户决定不作为本次收尾要求。

## Non-Goals

- 不重新修改协议实现或抓包结论；发布发现代码缺陷时退回对应子任务处理。
- 不删除 Docker volume、bench `data/`、账号 profile、workspace 或其他生产数据。
- 不为演练强制中断活跃请求，也不在旧镜像、旧 Compose 或数据库备份缺失时猜测继续。

## Key Decisions

- 发布产物以精确 SHA tag/digest 为准；`latest` 只有在确认指向同一 digest 后才能使用。
- SQLite 快照必须使用数据库 `.backup` / `.restore` API，并执行 `PRAGMA integrity_check`，
  不能直接复制在线数据库文件。
- cc2api 部署必须等待低连接窗口并 force recreate，不能只 restart；recreate 后完成 HTTP、
  DB 和设置检查，用户停测后不追加真实模型请求。
- 2026-09-05 用户确认取消完整回滚演练的收尾门禁；原 CHK-001 按范围调整关闭，
  不伪报补测通过，不修改通用部署规范。
- 联合回滚时先确定落在旧网关 allowed range 内的 `rollback_cli_version`，处理 bench 页面
  覆盖值后再回滚 cc2api；不能先回滚网关制造版本断层。
- 已有 run 的 `claude_code_version` 快照不随全局切换或回滚改写；不兼容时延后 continue
  或先恢复兼容网关。

## Key Context

- cc2api 目标提交为 `7aecda3`，父仓 gitlink/规范提交为 `c42d696`，均已推送到 `main`。
- 部署入口和约束位于 `.trellis/spec/cc2api/deploy/deploy-guidelines.md`，联合回滚契约位于
  `.trellis/spec/vibecoding-bench/deploy/remote-deploy.md`。
- 远程连接信息通常位于 `.deploy/cc2api.env`；任何输出、任务日志和上线证据都必须脱敏，
  不记录 Token、邮箱、Cookie、代理密码、完整 prompt 或完整响应正文。
- 协议任务的上线审计已归档到
  `.trellis/tasks/archive/2026-09/09-04-cc2api-claude-code-2-1-260-protocol/release.md`。

## Risks / Deferred

- 生产 recreate、数据库恢复和实际回滚具有外部副作用，必须以连接窗口、备份完整性和
  明确授权为门禁。
- 启动时条件迁移会更新仍等于 2.1.257 历史默认的值；必须证明管理员自定义 range、
  system-role、1M allowlist、模型策略和账号能力未被覆盖。
- 旧网关允许范围可能与已运行或待 continue 的 2.1.260 run 不兼容，联合回滚前必须先
  消除版本断层。
- 若目标镜像尚未构建完成或 digest 无法与提交闭合，停止部署并保留当前生产状态。

## Acceptance

- 目标镜像构建成功，生产部署 digest 与发布产物一致，容器 HTTP 和数据库完整性正常。
- 线上默认 profile/range 与账号 canonical env 为 2.1.260，自定义设置和账号能力与部署前
  摘要一致。
- 用户报告真实使用正常，既有协议和部署证据已核对，未逐项覆盖的生产请求如实记录。
- bench 默认版本和 run 快照已核对，continue 复用既有回归证据，不重跑生产测试。
- 已确认的旧镜像、DB 备份及版本协调记录保留；完整回滚演练未执行的说明已登记，
  不再阻塞本次收尾。

## Next Step

- 生产部署、迁移和配置保留检查已完成，用户报告真实 Claude Code 使用正常；部署证据
  见 [research/deploy-evidence.md](research/deploy-evidence.md)。
- 原演练阻塞已按用户决定取消，文档同步结果见 [check-report.md](check-report.md)。
  下一步提交记录并归档；用户停测约束继续有效，不主动发送模型请求或执行生产操作。
