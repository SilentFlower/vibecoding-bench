# 任务页默认账号与无白屏导航

## 目标

任务入口默认accounts，二级导航保持同一个iframe文档和正确历史。

## 事实与决定

Environments.vue默认tasks且key=source；内层runtime:navigate已提供同源导航协议。

## 验收

- [ ] 默认accounts、显式tasks、账号定位及全部二级Tab正确。
- [ ] 切换保持iframe文档身份，刷新/前后退恢复准确，迟到响应失效。

## 责任与边界

父任务11-14-task-account-runtime-followups统一承担共享入口接线和集成验收。本子任务维护上述交付的独立实现与验证证据。生产取证保持只读，模型测试使用合成输入及隔离回环。
