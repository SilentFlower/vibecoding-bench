# design.md

## Technical Design

### 范围

本任务只修改 vibecoding-bench 的抓包 run 链路：

- `webui/index.html`：完整抓包表单增加模型选择 UI。
- `webui/app.js`：收集并提交模型覆盖字段。
- `orchestrator/main.py`：请求 DTO、校验、run/task 字典透传、worker 环境变量。
- `images/worker/entrypoint.sh`：启动 `claude` 时追加 `--model`。
- `images/worker/Dockerfile`、`docker-compose*.yml`、`orchestrator/main.py`、worker usage 脚本默认版本：统一升级 `2.1.172`。

### 数据流

1. 用户在完整抓包表单的模型输入框中选择预置模型，或手填自定义模型名。
2. 前端提交 `model_override`：
   - 输入框非空时提交 trim 后的值。
   - 输入框为空则发送 `null` 或不发送。
3. 后端 `CaptureRunIn` 接收 `model_override: Optional[str]`。
4. 后端 trim 后校验：
   - 空字符串视为未覆盖。
   - 长度设置上限，避免异常大输入进入环境变量和命令行。
   - 仅允许模型名常见字符：字母、数字、点、下划线、连字符、方括号。
5. 后端把合法值放入抓包 task 字典。
6. `Runner.start_run` 对抓包 task 注入环境变量 `CLAUDE_MODEL_OVERRIDE`。
7. worker 使用数组式 shell 参数构造 `claude_args`，避免把模型名拼进 shell 字符串导致注入。
8. 启动 `claude` 时追加 `"${claude_args[@]}"`。

### 一次性语义

使用 `--model` 而不是修改 `settings.json`。原因：

- `--model` 是 Claude Code 当前会话级覆盖，天然符合“本次抓包”。
- 不需要在 `persist_runtime_claude_state` 前恢复 settings。
- 避免 SIGTERM、timeout、异常退出时把临时模型写回 `/mnt/profile/settings.json`。

### 运行留痕

为了回看抓包语境，模型覆盖写入 `runs.capture_model_override` 可选列，列表/详情接口沿用 `SELECT *` 自动返回。

### 兼容性

- 新字段缺失时等价于当前行为。
- 旧数据库通过 `_ensure_column` 补可空列。
- 普通 run、批量 run、continue/login/quota 路径不受影响。

## Rollout / Rollback

- Rollout：重建 orchestrator 和 worker 镜像，远程 recreate 后使用抓包表单 smoke test。
- Rollback：不填写模型覆盖即可恢复现有行为；必要时回退镜像。
