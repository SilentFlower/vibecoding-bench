# 技术设计

## 发布门禁

```text
抓包证据完成
  + cc2api 协议 Check-All 完成
  + 目标提交已推送并构建成功
  -> 低连接窗口部署
  -> DB/settings 与既有真实使用证据核对
  -> 备份保留、版本协调与未演练说明
```

## 快照

- cc2api：旧 image ID/digest、数据库 API 备份、profile/range、账号 canonical env、
  system-role/1M/模型策略摘要。
- bench：当前三镜像、`.env`、WebUI `claude_code_version`、DB 备份和 run 快照字段状态。
- 所有摘要脱敏，不输出 Token、邮箱或代理密码。

## 部署

- 使用精确 SHA tag/digest 核验产物，`latest` 仅在确认指向同一 digest 后使用。
- 部署前检查 established 连接和活跃 run，等待安全窗口。
- cc2api recreate 后完成 HTTP/DB 检查；用户停测后采用现有证据和用户真实使用反馈。

## 验收

- 版本身份：profile/range、账号 env、UA/telemetry。
- 行为：复用抓包与协议子任务的关键请求证据，记录用户实际使用反馈及未覆盖范围；不
  追加 bootstrap/hello、四模型或生产 continue 测试。
- 保留项：管理员自定义设置、1M allowlist、账号能力、bench run 版本快照。
- 日志：panic、migration、local version/system-role rejection、CCH/first-byte 异常分类。

## 回滚

- 按 2026-09-05 用户确认，本次保留旧镜像、数据库备份及操作边界，不执行完整联合
  回滚演练；该项不阻塞任务收尾。以下约束仅供将来实际故障回滚时使用。
- cc2api 回滚旧镜像和 DB/settings 快照，或先切 2.1.257 profile 作为快速降级。
- bench 已先行升级；若必须联合回滚，页面覆盖和 `.env` 均切到 cc2api 允许的 CLI，
  再回滚三镜像。
- 已有 run 的 `claude_code_version` 快照不随全局回滚改写，继续时按原版本执行；若原
  版本不在回滚网关允许范围内，应延后继续或先恢复兼容网关，不篡改历史 run。
