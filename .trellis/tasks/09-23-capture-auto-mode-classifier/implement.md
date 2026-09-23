# 实施计划

## 1. 正式抓包链路

- [x] 在 orchestrator 增加抓包权限模式类型、API 字段、run 列与幂等迁移。
- [x] 将权限模式快照传入 scheduler、worker 环境和 capture continue 路径。
- [x] 将 orchestrator、worker 与 WebUI 的允许值扩为 Claude Code 2.1.280 六种权限模式；持久 profile 默认保持不变。

## 2. WebUI 与文档

- [x] 抓包表单增加权限模式选择并提交字段。
- [x] 抓包详情显示实际权限模式。
- [x] 更新表单与 README，完整说明六种权限模式和 Plan classifier 边界。

## 3. 验证

- [x] 补充六模式 API、worker 校验、缺省、非法值、调度快照与 continue 继承测试。
- [x] 运行 orchestrator 单测、`bash -n images/worker/entrypoint.sh`、`node --check webui/app.js`。
- [x] 运行两份 Compose 配置检查和相关静态契约检查。
- [x] 执行 full Check-All，确认无未处理 CHK/FBK。

## 4. 发布与抓包

- [x] 精确提交本任务文件并推送 main，等待 GitHub Actions 三镜像构建成功。
- [x] 依照远端部署 SOP 拉取提交 SHA 镜像并 recreate orchestrator，完成健康与版本检查。
- [x] 通过正式 capture API 创建 2.1.280 / Opus 5.5 六模式矩阵，并创建 Opus 4.8、Sonnet 4.5 的 auto/plan 对照。
- [x] 核对每个 run 的指纹、OAuth profile、代理、sidecar 与目标 host，提取脱敏协议证据。
- [x] 对每条主请求复算 CCH 与 `cc_version`，比较 beta 顺序、body 字段和辅助请求，确认升级指南是否漂移。
- [x] 对额度、平台 rollout 或上游 unavailable 单独记录，不把它们误判为网关透传问题。

## 5. cc2api 同步

- [x] 按最终矩阵定义模型级普通/Auto/Plan beta 画像，不从模式名推断未观察行为。
- [x] 保留 `safeguards` 与未知 classifier context，原样转发 `safeguard_results` SSE。
- [ ] 运行 `cargo fmt --check`、`cargo test`、`cargo test cch`，提交并等待镜像构建后部署。

## 6. 脱敏证据摘要

- Opus 5.5 六模式、Opus 4.8 Auto/Plan、Sonnet 4.5 Auto/Plan 共 10 个正式 run 全部成功，
  目标请求均为 HTTP 200；run ID 与受限证据路径记录在 `capture-results.md`。
- 全部 billing 请求使用 `cc_version=2.1.280`，CCH 按 `0x4D659218E32A3268` 和 2.1.280
  全层级字符串 model 清空规则复算命中。
- Opus 5.5/4.8 仅 Auto、Plan 包含 `dangerous_tool_use` safeguards；两种模式的精确 beta
  相同，仅 `classifier_context.permission_mode` 分别为 `auto`、`plan`。
- Sonnet 4.5 Auto/Plan 均不包含 safeguards，普通 beta 追加 `message-threads-2026-08-12`。
- Sonnet 初始线程请求按最后一个 user text 确定性生成 `cc_version` 后缀；带
  `thread.previous_message_id` 的续轮复用同一会话级三位小写十六进制后缀，即使当前消息重新带 text。

## 风险位置

- `runs` 历史行为空值时的兼容解释。
- continue worker 漏传权限模式。
- CLI 覆盖误写回账号 profile。
- Auto Mode 不支持模型、额度不足或地区 rollout 导致无法得到成功结果。
