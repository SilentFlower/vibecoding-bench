# 技术设计

## 范围

本任务覆盖两个相关改动：

- WebUI / API / SQLite 增加普通运行和批量运行的 Claude Code 思考预算运行时配置。
- worker 修复 Claude API timeout 识别盲区，避免 `Request timed out` 被误判为成功。

## 运行时思考预算配置

新增 `app_settings` key：`claude_effort_level`。

后端新增接口：

- `GET /api/settings/runtime-effort`
- `PUT /api/settings/runtime-effort`

接口返回字段沿用默认模型配置风格：

- `configured_effort`：页面保存值；未配置时为 `null`
- `env_default_effort`：`.env` / orchestrator 环境兜底值
- `effective_effort`：实际用于普通 run / 批量 run 的值
- `allowed_efforts`：前端 select 使用的枚举

允许值固定为 `max`、`xhigh`、`high`、`medium`、`low`。保存空值表示删除页面覆盖并回退 `.env`。

`Runner.start_run()` 启动 worker 时：

- 普通 run / 批量 run 使用 `effective_runtime_effort()`。
- 抓包 run 继续使用 orchestrator 环境变量 `CLAUDE_CODE_EFFORT_LEVEL`，不读取页面配置。
- 账号 profile 默认 settings 仍只使用环境兜底，不写入页面覆盖值。

## WebUI

运行页在默认模型配置旁增加思考预算配置面板。

交互规则：

- 首次加载 runs 页时并行读取默认模型和思考预算配置。
- select 保存枚举值。
- “重置”提交空值，后端删除页面覆盖。
- 状态文案显示 `.env` 兜底值和当前生效值。

## API timeout 识别

`images/worker/entrypoint.sh` 保留现有 `CLAUDE_API_STALL_WATCHDOG_SEC` / `CLAUDE_API_STALL_MAX_RECOVERIES` 机制，只扩大识别来源：

- Claude JSONL 的 `system api_error` 连接错误继续支持。
- `.bench-transcript.log` 中的 `API error · Retrying ...` 或 `Request timed out · Retrying ...` 视为 API 卡死迹象。
- Claude JSONL 的 synthetic API error 终态，例如 `isApiErrorMessage=true` 且文本包含 `Request timed out`，视为失败终态。

失败终态处理：

- `classify_claude_completion` 返回新的非成功分类。
- 主循环写入 `.bench-status.json`，status 为 `failed`，error 包含 `Claude API 请求超时`。
- worker 以非 0 退出，orchestrator 按现有规则把 run 标为 `failed` 并读取错误信息。

## 兼容性

- 未配置页面覆盖时，默认行为保持 `.env` 的 `CLAUDE_CODE_EFFORT_LEVEL`，远端当前仍为 `max`。
- 已有 SQLite 不需要 migration；`app_settings` 是 key-value 表。
- 抓包 run 不受页面思考预算配置影响，避免影响抓包复现。
