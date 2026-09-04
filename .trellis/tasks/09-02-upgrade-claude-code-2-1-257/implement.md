# 实施计划

## 1. 完成 cc2api 协议子任务

- [ ] 激活 `09-02-cc2api-claude-code-2-1-257-protocol`。
- [ ] 完成 2.1.257 identity、Opus、Fable 5、Fable 5.1、Haiku 子画像与迁移。
- [ ] 完成 CCH / `cc_version` 抓包样本测试和首字节超时可观测性测试。
- [ ] 通过 cc2api Check-All。

## 2. 完成 vibecoding-bench 运行时子任务

- [ ] 激活 `09-02-vibecoding-bench-claude-code-2-1-257-runtime`。
- [ ] 同步 worker、orchestrator、Compose、WebUI、README 和部署规范默认版本。
- [ ] 覆盖普通 run、抓包、OAuth 登录和 quota worker 的版本传递测试。
- [ ] 通过 vibecoding-bench Check-All。

## 3. 完成发布子任务

- [ ] 确认两个实现子任务均完成并已推送可构建提交。
- [ ] 激活 `09-02-deploy-claude-code-2-1-257`，执行镜像发布与摘要核验。
- [ ] 备份生产数据库和设置快照，在低连接窗口升级 cc2api 与 vibecoding-bench。
- [ ] 完成 HTTP、容器、DB、运行版本、日志和 Fable 5.1 行为验收。
- [ ] 记录旧镜像与回滚证据，通过发布子任务 Check-All。

## 4. 完成 cli-bg 状态分类兼容子任务

- [ ] 激活 `09-02-cc2api-cli-bg-status-classifier`，完成默认放行/可切模拟的全局配置。
- [ ] 确认放行只绕过强特征请求的正文形状改写，账号 OAuth、header、proxy/TLS 和重试链路保持。
- [ ] 重新发布 cc2api，并通过 `proxy_url` 非空的固定账号执行真实代理链路非 429 验收。

## 5. 父任务集成收口

- [ ] 核对四个子任务 Acceptance 全部完成。
- [ ] 确认账号 `allow_1m_models` 未迁移，Fable `[1m]` 保持后续抓包待办。
- [ ] 更新协议与部署规范中的 2.1.257 可执行契约。
- [ ] 运行父任务最终 Check-All 并进入提交/归档流程。
