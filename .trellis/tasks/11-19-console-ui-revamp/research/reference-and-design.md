# 参考项目取证：codex-proxy-rs 与 @codex-proxy/ui

取证时间：2026-11-19。源码只读浏览于 `/tmp/refsrc/`（不入库）。两者均为 Apache-2.0。
**用户决定：不直接依赖 `@codex-proxy/ui`，参照其形态自建组件库，代码自行编写。**

## 1. 组件库形态（@codex-proxy/ui v0.12.0）

- Vue 3.5+ / TypeScript，经 GitHub Releases 的 tgz 分发（未上 npm），要求 Node 24+（本机 Node 22.23）。
- 导出分层：`.`（组件）、`./theme`（主题核心与运行时）、`./styles.css`、`./tailwind.css`、`./vite`、`./locale`。
- 组件 33 个：button、icon-button、card、page-header、sidebar、menu-item、segmented、input、input-number、input-tag、textarea、select、checkbox、radio、switch、slider、color-picker、date-picker、form、table、pagination、tag、empty、skeleton、loading、dialog、confirm-dialog、popover、dropdown、notification、scrollbar、markdown、motion-icon、config-provider。
- 主题模块分层：`core`（color / tokens / normalize / resolve）→ `derive`（colors / roles / components）→ `runtime/browser`（把 token 写成 CSS 变量）。
- 主题输入（`src/theme/types.ts`）：
  - `ThemeMode = system | light | dark`；`ThemePresetId = default | soft`（表面材质）。
  - 配色预设 4 个（relay-blue、deep-teal、signal-violet、graphite）或 `custom` 主色。
  - 种子颜色：success / warning / error / info / link / textBase / bgBase。
  - 种子尺寸：fontSize、sizeUnit、sizeStep、controlHeight、borderRadius、shadowStrength。
  - 组件覆盖：tableRowHeight、cardBorderRadius，另可 `tokenOverrides` 覆盖任意派生 token。
- 色阶派生依赖 `@ant-design/colors`、`@ant-design/fast-color`（思路同 antd v5 的 Seed → Map → Alias）。

## 2. 系统更新（codex-proxy-rs 前端）

- 无独立页面。入口在侧栏品牌区版本号按钮（`layout/components/AppSidebar.vue:220-238`）：常态灰底 `vX.Y.Z`；有更新时转成功色底并带 `ArrowUpCircle` 图标；侧栏折叠时底部出现同色图标按钮。
- 弹窗 `layout/components/system-update-modal/index.vue`：宽 48rem，标题「系统更新」+ 说明，成功色图标。
  1. 版本块（浅填充）：应用名、状态胶囊；4 个白色小格（当前版本、通道最新、构建、部署），最新版本格带「发布页」链接；错误 / 警告 / 可重试时间提示。
  2. 发布说明块：Markdown，最高 160px 滚动。
  3. 更新进度块（安装后出现）：终端图标 +「实时 / 断开」状态；日志行 = 时间 · 圆点 · [步骤] 消息，260px 滚动。
  4. 底栏：左侧更新通道分段 + 说明气泡；右侧「检查更新」+「下载更新 / 立即重启」。
- 进度来自后端实时日志流（SSE）；断线、解析失败、超时分别有文案。

## 3. 主题设置（codex-proxy-rs `/theme`，导航名「主题设置」）

- 页头：说明「自定义当前浏览器中的管理端主题」+「N 处修改待应用 / 已同步」；操作「撤销草稿」「恢复默认」「保存并应用」。
- 左侧 370px 编辑面板：全局 / 组件分段、Token 搜索。
  - 全局：主题模式（图标分段）、主题预设卡片、表面材质、颜色 / 尺寸 / 风格分类；颜色含品牌主色与功能色，可展开派生变量；尺寸含基础字号（11–17）、基础间距、尺寸步长；风格含通用圆角、阴影强度。
  - 组件：按钮、输入框、卡片与容器、表格、导航、布局与滚动等族的 Token。
- 右侧实时预览：真实组件在隔离环境渲染，首页画板 / 组件校样两种，可拖动平移、滚轮缩放。
- 侧栏底部另有深浅模式快捷切换。

## 4. 本项目第二版设计稿

- 源码：`research/design-v2/mock.html`、`mock.css`、`icons.js`（自 `.deploy/ui-revamp/after/` 复制；`mock.css` 字体路径已改为相对本目录）。打开 `mock.html#<画面>` 查看，画面名：accounts、account-edit、requests、proxies、environments、nodes、tasks、tokens、blocks、settings、update、update-progress、theme、mobile。
- 截图与改前 / 改后对照页在主工作区的 `/root/project/vibecoding-bench/.deploy/ui-revamp/`（git 忽略，仅本机可见，不在本 worktree 内）：`after/*.png`、`site/index.html`；第一版在 `after-v1/`。
