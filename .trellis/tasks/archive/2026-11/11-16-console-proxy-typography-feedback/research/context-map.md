# 实施上下文读取索引

本任务内联实施。此索引用于定位大规范中的权威段落，避免上下文自动注入截断。开始相应工作前读取原文，不能用这里的摘要替代原合同。

## UI权威段落

`.trellis/spec/web/frontend/ui-guidelines.md`：读取“视觉Token与层次”“控件行为”“宽屏与操作指针”“布局与信息组织”“完整视口弹窗与跨文档组件复用”“公共分页与原生运行工作区”“任务深层弹窗与工程现场一致性”。最新宽屏补充优先于早期1920px应用上限；本任务的字号升级以本次PRD与评审后的设计为新增决策。

## 账号身份与维护

`.trellis/spec/orchestrator/backend/account-runtime-v3.md`：读取开头固定账号环境合同、“v3凭据单一所有者与交接协议1”“v3独立账号动作、真实进程指标与完整转发验收”“代理引用与有界日志读取补充”。代码核对`proxy_sync.py`、`main.py::_runtime_owner_transition/v3_quiesce`、`account_runtime.py::_account_lock`及网关`router.rs::config_permit`。

- 内部源摘要只用于服务端；公开选择版本必须不透明且绑定实际任务、关系与连接。
- `synchronize_proxy`当前把源变化当作后台任务已完成；新的交互保存必须返回冲突或经回读确认目标已经生效。
- 独立任务支持直连，关联任务沿网关权威。既有环境、登录、所有权和部署门禁保持。
- 读代理选择不发模型请求；验证使用合成账号和本地替身。

## 原型与现有验证入口

`doc/design/flower2api-concept.html`中`workProxyCompact/openWorkProxySwitch/saveWorkProxySwitch`给出专用换线的现有交互。旧正式行为由`verify_task_feedback.py`覆盖完整账号窗口，本任务应将对应断言升级为专用窗口的载荷/取消/焦点断言。

`verify_task_login_design.py`覆盖目录选择、Esc、手动兼容；`verify_proxy_design.py`覆盖目录管理与账号选线；`verify_shared_pagination.py`覆盖公共控件；`verify_native_environments.py`覆盖原生环境。保留这些业务断言，字号相关预期按本任务新基准更新。
