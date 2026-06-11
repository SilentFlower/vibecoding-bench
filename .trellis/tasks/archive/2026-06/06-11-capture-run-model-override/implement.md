# implement.md

## Implementation Checklist

- [x] 读取 Trellis backend/frontend/deploy/spec 指南和现有抓包 run 代码。
- [x] 升级 Claude Code 默认版本到 `2.1.172` 并全局搜索确认无旧默认残留。
- [x] 后端新增 `CaptureRunIn.model_override`、校验函数、runs 可选列和 task/env 透传。
- [x] worker 启动 `claude` 时以安全参数数组追加 `--model`。
- [x] 前端完整抓包表单新增预置模型输入框，支持下拉选择和手填自定义值。
- [x] 运行详情或抓包信息展示本次模型覆盖。
- [x] 执行验证命令并检查 diff。

## Validation

- `python3 -m py_compile orchestrator/main.py`
- `bash -n images/worker/entrypoint.sh`
- `node --check webui/app.js`
- `git diff --check`
- 视情况启动本地服务手动验证抓包表单提交 payload。

## Review Gates

- 确认 `--model` 只作用于本次 worker 进程，不写回 profile。
- 确认模型名不会通过 shell 拼接造成注入。
- 确认 `2.1.172` 在 Dockerfile、compose、orchestrator、usage UA 保持一致。
