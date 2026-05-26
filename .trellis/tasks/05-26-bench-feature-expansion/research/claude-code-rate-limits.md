# Claude Code 额度信息调研

## 来源

* Claude Code 状态栏文档：`https://docs.anthropic.com/en/docs/claude-code/statusline`
* Claude Code Pro/Max 帮助文档：`https://support.claude.com/en/articles/11145838-using-claude-code-with-your-pro-or-max-plan`

## 结论

* Claude Code status line 会把 JSON 传给本地脚本，字段包括 `rate_limits.five_hour.used_percentage`、`rate_limits.five_hour.resets_at`、`rate_limits.seven_day.used_percentage`、`rate_limits.seven_day.resets_at`。
* 文档明确这些字段仅 Claude.ai Pro/Max 订阅用户在首次 API 响应后出现；脚本应处理字段缺失。
* Pro/Max 的 Claude 与 Claude Code 共用使用限制，Claude Code 官方帮助建议用 `/status` 监控剩余额度。
* 当前公开文档没有看到单独的 `seven_day_sonnet` 或类似字段。用户提到的“7d sonnet 额度”可能来自 TUI `/status` 输出或内部未公开状态，需要用真实账号验证。

## 对本项目的映射

* 最稳的查询方式是为账号启动一次经过 sidecar SOCKS5 的轻量 Claude TUI 会话，注入临时 `statusLine` 脚本，把收到的 status JSON 写到 `/workspace/.bench-quota.json`，再读取该文件。
* 该方式仍会经过账号 SOCKS5，因为 worker 共享 sidecar network namespace。
* 该方式可能需要触发一次 API 响应，才能拿到 `rate_limits` 字段；可以用极短 prompt，但这会消耗少量额度。
* 如果必须拿“7d Sonnet 单独额度”，需要另做实验：运行 `/status` 或切换模型后观察 TUI / transcript / status JSON 是否出现模型级字段。
