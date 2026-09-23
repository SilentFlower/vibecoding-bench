# 实施计划

## 1. 正式抓包链路

- [ ] 在 orchestrator 增加抓包权限模式类型、API 字段、run 列与幂等迁移。
- [ ] 将权限模式快照传入 scheduler、worker 环境和 capture continue 路径。
- [ ] 在 worker entrypoint 校验允许值，并向 Claude CLI 追加 `--permission-mode`；持久 profile 默认保持不变。

## 2. WebUI 与文档

- [ ] 抓包表单增加权限模式选择并提交字段。
- [ ] 抓包详情显示实际权限模式。
- [ ] 更新 README 的抓包说明和 Auto Mode 使用边界。

## 3. 验证

- [ ] 补充 API 缺省、Auto、非法值、调度快照与 continue 继承测试。
- [ ] 运行 orchestrator 单测、`bash -n images/worker/entrypoint.sh`、`node --check webui/app.js`。
- [ ] 运行两份 Compose 配置检查和相关静态契约检查。
- [ ] 执行 full Check-All，确认无未处理 CHK/FBK。

## 4. 发布与抓包

- [ ] 精确提交本任务文件并推送 main，等待 GitHub Actions 三镜像构建成功。
- [ ] 依照远端部署 SOP 拉取提交 SHA 镜像并 recreate orchestrator，完成健康与版本检查。
- [ ] 通过正式 capture API 创建 2.1.280 / Opus 5.5（必要时用受支持低额度模型复核）的 Auto run。
- [ ] 核对 run 的指纹、OAuth profile、代理、sidecar 与目标 host，提取脱敏协议证据。
- [ ] 对额度、平台 rollout 或上游 unavailable 单独记录，不把它们误判为网关透传问题。

## 风险位置

- `runs` 历史行为空值时的兼容解释。
- continue worker 漏传权限模式。
- CLI 覆盖误写回账号 profile。
- Auto Mode 不支持模型、额度不足或地区 rollout 导致无法得到成功结果。
