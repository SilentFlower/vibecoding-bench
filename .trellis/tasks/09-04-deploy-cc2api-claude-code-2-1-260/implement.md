# 实施计划

## 1. 发布前检查

- [x] 确认抓包与协议子任务完成，目标提交已推送且镜像构建成功。
- [x] 记录 cc2api 旧镜像、bench 当前 tag、连接、运行配置和数据库/settings 摘要。
      旧 bench 三镜像追加核验随完整演练一并取消，保留未执行说明。
- [x] 使用数据库 API 备份并验证 integrity。

## 2. cc2api 部署

- [x] 核对 SHA tag、`latest` 和 digest 一致。
- [x] 等待低连接窗口，pull 并 force recreate cc2api。
- [x] 核验容器、HTTP、DB、profile/range、账号 canonical env 和设置保留。

## 3. 真实请求验收

- [x] 记录用户实际使用正常的反馈，复用已有抓包和协议证据并说明未覆盖范围。
      bootstrap/hello 和四模型逐项生产测试不再追加。
- [x] 检查版本拒绝、system-role、CCH、迁移、panic 和流式异常日志。
      分窗口记录，保留手工请求 429，不能描述为所有日志无错误。
- [x] 核验 bench 默认 2.1.260、run 快照分布与既有 continue 回归证据。
      未重新启动生产 continue，按用户决定不要求补跑。

## 4. 回滚与记录

- [x] 核对已记录的 2.1.257 profile/allowed range、旧网关镜像和备份完整性。
- 完整联合回滚演练：未执行，用户已取消本次要求，不作为待办或阻塞项。
- [x] 记录 DB/镜像恢复路径以及历史 run 快照与旧网关范围冲突的处理规则。
- [x] 完成 Check-All 与 release evidence，并同步父任务中的收尾决定。
- [ ] 完成提交、归档及父任务结果汇总。

## 5. 本轮收尾

- [x] 回收本机会话中的原始部署结果并写入 `research/deploy-evidence.md`。
- [x] 写入 `release.md` 和 `research/rollback-plan.md`，如实保留未执行说明。
- [x] 静态 Check-All：任务材料、引用、发布证据、回滚契约；不调用模型或生产服务。
      原 `CHK-001` 随用户确认的范围调整关闭；本轮仅核对文档同步，详见 `check-report.md`。
- [x] 静态检查结果落盘并保存任务进度；保持 `in_progress`，未标记 completed。
      下一步进入提交与归档收尾，不再要求补做演练。
