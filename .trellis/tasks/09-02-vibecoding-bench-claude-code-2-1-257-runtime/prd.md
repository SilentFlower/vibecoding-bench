# 升级 vibecoding-bench 到 Claude Code 2.1.257

## Goal

将 vibecoding-bench 所有无页面覆盖的新 worker 默认 Claude Code 版本统一升级为
2.1.257，同时保持 WebUI 运行时覆盖优先级、抓包隔离规则和启动时版本校验不变。

## Requirements

- `images/worker/Dockerfile` 预装 Claude Code 2.1.257。
- `images/worker/entrypoint.sh` 的 shell 与 Node fallback 均使用 2.1.257，实际
  `claude --version` 不一致时仍安装指定版本，安装失败必须让 worker 失败。
- `orchestrator/main.py` 的环境兜底与内嵌 Node 脚本 fallback 使用 2.1.257；WebUI
  SQLite 保存值继续优先于 `.env`，清空页面值后回退环境默认。
- 普通 task、抓包 run、OAuth/login worker 和 quota worker 均显式传递最终
  `CLAUDE_CODE_VERSION`，不依赖镜像偶然预装版本。
- `docker-compose.yml`、`docker-compose.remote.yml`、`.env.example` 的默认值同步为
  2.1.257。
- `webui/index.html` 的 placeholder 与 datalist 首选值更新为 2.1.257，保留旧版本作为
  可手动输入的回滚示例。
- `README.md` 与 Trellis 部署规范更新默认版本说明，但不改变页面覆盖的优先级语义。
- 不修改模型选择、`[1m]` 账号策略、抓包内容或 cc2api 协议画像；这些由兄弟子任务
  负责。

## Acceptance Criteria

- [ ] 全仓除历史任务、历史日志、回滚示例和 cc2api 子模块外，不再存在作为当前默认值
      的 `2.1.220`。
- [ ] worker 镜像构建参数、entrypoint shell/Node fallback、orchestrator fallback、两份
      Compose 和 `.env.example` 均为 2.1.257。
- [ ] 无页面覆盖时 API 返回 `env_default_version=effective_version=2.1.257`；保存页面
      覆盖后使用覆盖值，清空后恢复 2.1.257。
- [ ] 普通 task、抓包、OAuth/login 和 quota worker 创建参数均包含预期版本。
- [ ] entrypoint 仍拒绝非法版本号，版本安装失败不会静默回退。
- [ ] `python -m unittest orchestrator.test_main`、Compose config 校验和相关静态检查通过。

## Out of Scope

- 不构建、推送或部署镜像；由发布子任务执行。
- 不修改当前生产 WebUI 已保存的覆盖值；发布时单独核对是否需要更新。
- 不修改 Claude 模型默认值、effort、代理或凭据恢复逻辑。
