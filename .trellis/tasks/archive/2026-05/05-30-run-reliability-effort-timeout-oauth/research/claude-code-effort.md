# Claude Code 思考预算配置调研

## 结论

- Claude Code 支持通过环境变量 `CLAUDE_CODE_EFFORT_LEVEL` 设置 effort。
- 官方模型配置文档中，settings 的 `effortLevel` 支持 `low`、`medium`、`high`、`xhigh`。
- 当前项目硬编码 `CLAUDE_CODE_EFFORT_LEVEL=max`，不适合作为批量自动跑默认值；默认改为 `xhigh` 更符合用户要求，并保留 `.env` 覆盖能力。

## 参考

- https://code.claude.com/docs/en/model-config
- https://code.claude.com/docs/en/settings
