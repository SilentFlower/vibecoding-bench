# 代码与截图证据

## 加载流程

- `apps/web/src/components/TasksWorkspace.vue:79` 等待 `api.openRuntime()` 后才装入模板；`receive(runtime:ready)` 后隐藏整页加载状态。模板可见性由 `.runtime-connecting>.task-runtime` 控制。
- `apps/legacy-web/app.js:244` 把当前路由初始化与 `document.fonts.ready` 合并等待。`:409` 把正式账号和登录草稿绑定为一个首屏读取。`:3126` 还需完成 `/runtime/api/auth/me`，`:3200` 后才导航。
- `apps/legacy-web/projects.js:130` 首批请求完成后顺序等待模型配置及账号快照/历史等数据，当前整页显示也被这些读取拦住。
- `RuntimeEnvironments.vue:78` 先交换会话，再读列表。`:76` 的 CPU 读取已经在列表返回后后台运行，必须保持该行为和换代保护。
- `services/orchestrator/main.py:12686` 的环境列表按环境串行补充角色、内核、CRIU、采集等状态；`account_runtime.py:536` 逐角色 Docker 读取。身份与开关快照已有非阻塞锁合同，优化需保留。
- 当前会话使用真实生产构建与离线合成接口验证：任务页基准506ms；登录草稿增加1500ms后2108ms；字体增加1500ms后1953ms；环境页基准314ms；环境列表增加1500ms后1906ms。以上是合成延迟证据，线上最慢接口耗时尚待测量。

## 任务界面

- `apps/legacy-web/index.html:25/35`、`app.js:2999/3197`、`TasksWorkspace.vue:79` 维护明暗偏好；`console.css:13`、`approved-design.css:184` 和 `work-design.css:179` 含暗色专用覆盖。当前用户要求替换旧规范中的保留偏好约定。
- 六个主入口在 `index.html` 的主导航中。原型 `doc/design/flower2api-concept.html:1231` 和 `work-design.css` 是现有视觉来源。
- `index.html` 的终端 footer 有 `data-show-project-pane="history"`，与已有交付历史分区重复。保留历史分区与冻结交付入口，移除终端中的重复按钮。
- `projects.js:588` 设置 `projects-target-label`；模板给该元素 `env-sr-only`，该类只在 `environments.css:189` 的 `.environment-page` 下隐藏，解释截图3的裸文本。
- `work-design.css:759` 把交付窗口限制在920×760，`:770` 又限制源码预览最大380px，文件列表与外层正文叠加滚动。
- `projects.js:884-912` 的交付读取保护账号、页面、候选选择及文件选择代次，排版调整必须保持这些判断。

## 系统更新

- `SystemUpdates.vue:248-259` 同时展示发布摘要、平台信息、兼容说明和安装入口；当前与最新相同仍保留禁用的安装计划按钮。
- `toggleLatestNotes()` 通过 DOM 同时打开 `.approved-maintenance`，使完整说明与环境概况、维护记录及版本列表耦合。
- `SystemUpdates.vue:255-289` 在同一个 details 中连续放置概况卡片、操作状态和版本列表，间距和信息优先级不足。
- `releaseHighlights` 将每段第一行作为标题，单行长段落变成大段加粗文字。完整发布原文必须保持可达，概览应使用正常正文层级。
