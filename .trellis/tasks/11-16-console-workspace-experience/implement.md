# 实施计划

## 执行顺序

- [x] 固化五张截图对应夹具、首屏合成延迟基线与并发断言。
- [x] 调整工作区框架/区域可见性、会话并发合并和账号/草稿/工程现场独立读取。
- [x] 提取环境只读投影，采用最多3个工作者并核对排序、上下文、维护锁和异常语义。
- [x] 移除主题切换和暗色专用代码，更新原型及原暗色断言。
- [x] 调整六个主入口、交付入口与最近目标卡片，保持原导航和记录可达性。
- [x] 实现全高验收阅读布局与源码/报告切换，保留冻结请求保护。
- [x] 重排系统更新状态、说明、平台、维护和历史，独立控制展开，同步对应原型。
- [x] 完成三视口与两个入口的统一回归，记录实际耗时和截图，执行Check-All、规范更新与精确Git计划。

## 定向验证

- `npm --prefix apps/web run build`
- 新增慢会话/慢字体/慢草稿/慢历史、失败重试与后端有界并发测试，覆盖会话去重、过期、字段、排序和维护锁。
- 运行`test_account_runtime.py`中的环境列表、身份与维护用例并补充并发回归。
- `.venv/bin/python deploy/flower2api/verify_native_environments.py`
- `.venv/bin/python deploy/flower2api/verify_environment_cpu_summary.py`
- `.venv/bin/python deploy/flower2api/verify_management_ui.py --output .deploy/console-workspace-experience/management`
- `.venv/bin/python deploy/flower2api/verify_runtime_workspace_design.py`
- `.venv/bin/python deploy/flower2api/verify_project_workspace_design.py`
- `.venv/bin/python deploy/flower2api/verify_task_account_config.py`
- `.venv/bin/python deploy/flower2api/verify_update_design.py`
- `.venv/bin/python deploy/flower2api/verify_system_update_browser.py --output .deploy/console-workspace-experience/system-update`
- `.venv/bin/python deploy/flower2api/verify_dashboard_update.py`
- `.venv/bin/python deploy/flower2api/verify_dialog_typography.py`

## 统一验收与回退

覆盖1440×900、1280×720与390×844，核对工程/养号、深链接、历史导航、键盘焦点、未完成表单、长文本/路径/报告、真实未知与失败。旧回执失效、CPU换代、候选冻结、取消零写入、回退/恢复合同作为重点回归。

严格视觉断言同步用户新设计及对应原型，行为断言持续保留。按加载、后端并发、任务界面、验收窗口和更新布局分段审查，可分别回退。本任务统一拥有实现、检查、规范和交付记录。
