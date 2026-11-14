# 任务Claude CLI默认关闭遥测与环境配置

## 目标

官方CLI默认关闭遥测，并支持部署环境off/on配置。

## 事实与决定

当前CLI环境和账号settings仅设置DISABLE_AUTOUPDATER。官方遥测关闭键按非空值解释，开启需要移除关闭键。

## 验收

- [ ] V3_CLI_TELEMETRY缺省off，显式off/on和非法值行为明确。
- [ ] 任务、项目/Pi、养号和交互CLI实际环境及settings一致；on清理关闭键，自动更新关闭项继续存在。

## 责任与边界

父任务11-14-task-account-runtime-followups统一承担共享入口接线和集成验收。本子任务维护上述交付的独立实现与验证证据。生产取证保持只读，模型测试使用合成输入及隔离回环。
