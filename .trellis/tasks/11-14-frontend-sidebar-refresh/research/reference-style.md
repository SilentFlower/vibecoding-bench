# 参考项目运行时设计取证

来源：公开演示 https://codex-proxy-rs.ainz.cc/ ，使用 README 公共演示账号，只查看页面。1440×1000 浏览器截图与数据保存在 `.deploy/frontend-sidebar-refresh/reference/dashboard.png`、`runtime-design.json`。

## 色板

正文为 rgb(14,23,38)，次级文字 rgb(65,75,90)/rgb(95,104,118)，白色表面与 rgb(248,249,252) 浅灰底色；蓝色交互强调。现概念稿正文较浅且间距大，先强化文字层级；品牌与布局方向尚待用户继续反馈，颜色不全量跟换。

## 字体三层

- 参考实际加载 Inter Variable（Latin WOFF2）用于界面文字；正文常见13px/400/19.5px，标签12px/650–700，标题20px/760/23px。
- 实际加载 JetBrains Mono Variable（Latin WOFF2）用于数字与技术标识；指标28px/760，数据12px/650–760。
- 中文走 ui-sans-serif/system-ui 的系统字体回退。当前概念稿只声明 Inter，页面未加载字体文件；英文实际回退。中文样式统一明确使用 Microsoft YaHei UI / PingFang SC / Noto Sans CJK SC，并按平台回退。
- 新稿使用内嵌授权字体以保持离线一致性；正文/导航14px、辅助12px、正文行高1.5，中文标题24px/650。数字采用等宽且启用tabular-nums。

## 形状与组件

参考控件6–8px圆角、0边框；卡片18px、0边框，轻阴影 rgba(14,23,38,.08) 0 10px 22px -18px。参考按表面层次区分，现稿边框较多。当前先处理用户明确指出的字体与侧栏，不整体改变已探索结构。

## 动效与状态

运行时捕获 sidebar-signal 动画520ms一次。概念稿只保留短的交互过渡并支持reduced-motion。折叠须保持所有导航与系统更新入口可达，提供title及aria-label，刷新恢复折叠偏好。

## 对照验收

1440/390px截图；检查document.fonts与数字实际字体；正常/折叠状态导航、品牌更新入口、键盘按钮、刷新偏好；现有搜索/详情编辑/更新模拟继续验证。
