# 上线操作

## 结论

存在上线操作。本任务只完成代码、配置默认值和测试更新，实际镜像发布、生产部署及线上验证由
`09-02-deploy-claude-code-2-1-257` 子任务负责。

## 已核对证据

- `task.json`
- `prd.md`
- `design.md`
- `implement.md`
- `implement.jsonl`
- `check.jsonl`
- 业务提交 `9ed24dd`

## 漂移检查

此前缺少 `release.md`。任务材料和业务提交均明确包含 worker 镜像、orchestrator、两份
Compose、环境变量、WebUI 版本覆盖及部署文档变更，因此不能按“无上线操作”处理。

## SQL 变更

无。

## 配置变更

- 生产 `.env` 的 `CLAUDE_CODE_VERSION` 应核对并设置为 `2.1.257`。
- WebUI SQLite 中保存的 Claude Code 版本覆盖值优先于 `.env`；部署前必须读取当前保存值，
  若仍为旧版本，应明确更新为 `2.1.257` 或清空以回退环境默认。
- 不修改模型、effort、代理、账号凭据或 `[1m]` 策略。

## 批处理、部署脚本与数据修复

- 等待 `main` 对应的 GitHub Actions 三镜像构建完成，并确认 orchestrator、worker、sidecar
  使用同一个不可变 SHA tag。
- 生产服务器拉取该 SHA tag 的三镜像，并按远程部署规范重建 orchestrator 服务。
- 无数据修复脚本。

## 外部系统与依赖平台

- GitHub Actions / GHCR：负责构建和提供三镜像。
- 生产服务器：负责拉取镜像、更新配置、重建服务和执行线上验证。

## 上线顺序

1. 确认三镜像的同一 SHA tag 均已发布。
2. 记录当前生产镜像 tag、`.env` 和 WebUI 保存的版本覆盖值，作为回滚基线。
3. 更新生产 `.env` 和 WebUI 保存值，使最终生效版本为 `2.1.257`。
4. 拉取三镜像并重建 orchestrator。
5. 执行 API、worker 和真实调用验证。

## 回滚说明

- 同时回滚 orchestrator、worker、sidecar 三镜像到部署前的同一 tag。
- 恢复部署前的 `.env` 和 WebUI Claude Code 版本覆盖值。
- 不能只回滚镜像或只回滚环境变量，否则 orchestrator 与 worker 的目标版本可能不一致。

## 上线后验证

- 版本配置 API 的 `env_default_version` 和 `effective_version` 符合预期；若存在页面覆盖，
  `configured_version` 应与发布决策一致。
- 新启动的普通 task、完整抓包、login、quota 和 OAuth refresh worker 均收到
  `CLAUDE_CODE_VERSION=2.1.257`。
- worker 内执行 `claude --version` 返回 `2.1.257`，且启动日志没有安装失败或版本不匹配。
- 使用发布任务定义的真实账号与模型场景验证 fable 5、fable 5.1 及 `[1m]` 请求；本任务不改变
  模型映射或账号策略。
