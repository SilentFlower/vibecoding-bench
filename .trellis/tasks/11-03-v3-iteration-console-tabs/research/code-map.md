# 现有导航与共享组件

## 已确认入口

| 文件定位 | 事实 |
| --- | --- |
| webui/index.html:40 | 顶层并列 #projects“项目迭代”和 #warmup“养号迭代” |
| webui/index.html:71 | 两者共用 tpl-projects，内部已有终端/交互记录页签 |
| webui/app.js:56 | renderProjects 使用 ProjectsUI.mount 的默认 projects 空间 |
| webui/app.js:66 | openWarmupAccount 通过临时 accountId 与 #warmup 只读进入 |
| webui/app.js:73 | renderWarmup 使用 namespace=warmup |
| webui/app.js:81 | ROUTES 分别登记 projects、warmup |
| webui/app.js:97 | navigate 更新 viewGeneration，重建 DOM、关闭弹窗/旧订阅 |
| webui/projects.js:45 | mount 先 unmount，再按 namespace 固定 servicePath 并注册处理器 |
| webui/projects.js:102 | mount 支持预选 accountId，不可用时显示错误 |
| webui/projects.js:116 | unmount 增加 revision/selection，关闭 SSE、时钟，并清空账号/分页 |
| webui/projects.js:212 | selectAccount 重新读取当前空间现场；后续异步回调按 revision 和账号校验 |

## 边界

- 两个空间分别请求 /projects、/accounts/warmup/pi；已有后端分离与状态契约不变。
- 当前组件为原生 JS，不引入框架或新构建链。
- URL 是当前模式/账号的唯一持久导航来源；不把路由复制进 localStorage/state 形成第二套权威。
- 仅保存账号与模式，不保存或跨空间复制未提交表单。
- 保留原终端/事件内页签，新增的空间切换位于其上层。

## 验证入口

- deploy/v3/verify_project_browser.py：入口存在，但当前夹具仍访问旧 project-batch DOM；实施时按现有 ProjectsUI 与 /projects、/accounts/warmup/pi 实际契约更新，保留真实浏览器/HTTP/SQLite 证据。
- deploy/v3/verify_browser.py、verify_stack.py 的 --browser --project-iteration：统一后台和页面验证基础。
- 前端规范要求资源显式收口、慢回包失效、深浅主题、窄屏和真实浏览器验证。
