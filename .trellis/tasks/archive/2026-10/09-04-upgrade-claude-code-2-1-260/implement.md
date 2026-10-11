# 实施计划

## 1. bench 全量升级与发布

- [ ] 完成子任务 `09-04-vibecoding-bench-claude-code-2-1-260-runtime`。
- [ ] 同步所有运行时默认值和 worker 创建路径到 2.1.260。
- [ ] 为 `runs` 增加版本快照，修复 continue 使用当前全局版本的问题。
- [ ] 通过 bench Check-All，构建三镜像并部署到生产。
- [ ] 验证新 run 为 2.1.260，旧 run 继续遵守自身版本快照。

## 2. 用户抓包与证据分析

- [ ] 等待用户提供生产 run ID 与模型对应关系。
- [ ] 完成子任务 `09-04-claude-code-2-1-260-capture-evidence`。
- [ ] 输出脱敏 identity、endpoint、beta、body、`cc_version`、CCH、bootstrap 和
      telemetry 差异，以及 cc2api 实施输入。

## 3. cc2api 协议适配

- [ ] 完成子任务 `09-04-cc2api-claude-code-2-1-260-protocol`。
- [ ] 新增 2.1.260 默认画像并保留 2.1.257 回滚画像。
- [ ] 完成抓包驱动的模型子画像、设置迁移和回归测试。
- [ ] 通过 Rust、CCH、Web 构建和 Check-All。

## 4. cc2api 发布与集成验收

- [ ] 完成子任务 `09-04-deploy-cc2api-claude-code-2-1-260`。
- [ ] 发布并部署 cc2api，核验 DB/settings 版本分布、HTTP、日志和真实请求。
- [x] 同步本次不做完整回滚演练的用户决定，保留已确认的备份与版本协调记录。
      演练未执行，不记作通过；原部署子任务 CHK-001 不再阻塞收尾。
- [ ] 汇总四个子任务结果，完成父任务最终 Check-All。

## 验证重点

- bench：`python3 -m unittest orchestrator.test_main`、两份 Compose config、版本默认值
  审计、生产 worker 实际版本与 continue 快照回归。
- cc2api：`cargo fmt --check`、`cargo test`、`cargo test cch`、`npm run build`。
- 发布：复用已有镜像摘要、页面覆盖、DB 快照、账号版本分布、日志和用户实际使用记录。
- 本次收尾只更新、提交与归档记录，不重复上述测试；完整回滚演练未执行且已取消要求。
