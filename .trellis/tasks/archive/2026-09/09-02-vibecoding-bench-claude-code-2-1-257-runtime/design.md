# 技术设计

## 设计目标

维持现有版本优先级，只替换“未配置时的默认值”：

```text
WebUI SQLite 覆盖值
  -> 若为空，使用 orchestrator 环境 CLAUDE_CODE_VERSION
  -> 若环境未配置，使用代码 / Compose 默认 2.1.257
  -> worker entrypoint 校验实际 claude --version，不一致则安装目标版本
```

## 变更范围

- 镜像层：`images/worker/Dockerfile`。
- worker 启动层：`images/worker/entrypoint.sh` 的 shell 默认值和写凭据 Node 脚本默认值。
- orchestrator：`orchestrator/main.py` 顶层环境 fallback，以及 OAuth/login、quota 等
  内嵌 Node 脚本 fallback。
- 配置层：`docker-compose.yml`、`docker-compose.remote.yml`、`.env.example`。
- UI/文档：`webui/index.html`、`README.md`、vibecoding-bench 部署规范。
- 测试：`orchestrator/test_main.py` 与 Compose config 检查。

## 行为保持

- `effective_claude_code_version()` 的优先级不变。
- 所有 worker 类型继续显式传递版本环境变量。
- 抓包 run 不继承模型页面覆盖的现有隔离语义不变；本任务只处理 CLI 版本。
- worker 版本格式校验和 npm 安装失败处理不变。
- OAuth refresh 请求的 UA 特殊规则不变；只更新确实使用 Claude Code UA 的调用。

## 测试设计

- 更新默认版本断言，并增加 API 返回 env/effective version 的无覆盖、覆盖和清空用例。
- 对普通 task、capture、OAuth/login、quota 的容器创建参数断言
  `CLAUDE_CODE_VERSION=2.1.257`。
- 检查 entrypoint 中 shell 与 Node fallback 一致，避免部分恢复路径继续写 2.1.220。
- 运行两份 Compose 的 `config --quiet` 和镜像解析，确认三镜像仍共享同一 tag。
- 使用 `rg` 审计当前默认字符串；历史文档与明确回滚示例不机械替换。

## 回滚

源代码回滚会恢复旧默认；已通过 WebUI 保存的显式版本不随代码回滚改变。生产层应同时
回滚三镜像 tag 和 `.env`，否则旧 orchestrator 与新 worker 镜像可能出现默认值不一致。
