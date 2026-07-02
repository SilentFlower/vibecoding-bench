# Quality Guidelines

> 本项目前端的代码质量与评审标准。

---

## Overview

前端代码质量目标按优先级:

1. **零构建保活**(不引 npm / 构建工具,改完保存浏览器刷新即可)
2. **跨主题正常**(暗 / 明两套都要看着合理)
3. **无 XSS**(任何用户数据进 DOM 必过 `escapeHTML`)
4. **快捷键 + Esc 不断**(终端实验室皮肤的灵魂)
5. **可被未来 AI 看懂**(命名一致、节顺序固定、中文注释 WHY)

**故意没有**:lint 配置、Prettier、单元测试、Storybook、e2e。质量靠人工 review + 真跑(浏览器点全路径)。

---

## Forbidden Patterns

| 模式 | 为什么禁止 |
|------|-----------|
| 引入 npm / package.json / 构建工具(webpack / vite / rollup / parcel) | 零构建是本项目的核心约束;真要引必须先在团队拉齐 |
| 引入框架(React / Vue / Svelte / lit-html) | 三个文件 + 4 个 tab 不值得引框架 |
| 引入 CSS 框架(Tailwind / Bootstrap / Bulma) | 风格已锁定为"终端实验室皮肤",外来工具类会破坏一致性 |
| 引入打包 CSS 处理器(Sass / Less / PostCSS) | 同上,且需要构建 |
| 引入 JavaScript 工具库(jQuery / Lodash / Underscore) | 需要的工具(`$ / $$ / escapeHTML / formatSize`)就 5 行,自己写 |
| `console.log` 留到提交 | 噪音,且暴露 internals 给打开 devtools 的用户 | 调试完删,真要留就接 `console.warn/error` 且加 `[bench]` 前缀 |
| `console.error` 当唯一错误反馈 | 用户看不到 devtools | 用户可见错误一定要 `alert(...)` 或更好的 toast(P2) |
| 在 render 字符串里嵌入用户输入不 escape | XSS | `escapeHTML(...)`,见 type-safety.md |
| `document.write` / `eval` / `new Function(str)()` | 危险 / 已废 / 性能差 | 用 DOM API 或 JSON.parse |
| 直接写颜色 hex(`color: #ffb649`)在新 CSS 规则里 | 主题切换失效,且重复定义颜色 | 永远用 `var(--amber)` 等 CSS variable |
| 给元素加 `border-radius` | 全局 `border-radius: 0 !important` 已强制,但新组件别在 `style` 里硬上 | 跟随终端皮肤,无圆角 |
| inline `style="..."` | 难维护、覆盖 CSS variable | 抽 class 到 style.css |
| 用 `<div onclick>` 模拟按钮 | a11y 差、键盘不友好、无 type | 用真 `<button type="button">` |
| 在 SSE / WebSocket 消息回调里 `await API(...)` | 1Hz 推 × 嵌套请求 = 流量灾难 | 推送已是全量,直接渲染 |
| 用 `setInterval` 轮询替代 SSE | 浪费 + 状态可能漏 | runs 走 `/api/runs/stream` |
| `addEventListener` 在 render 函数里反复绑 | 累积 listener,触发 N 倍 | 用 `el.onclick = ...` 覆盖式;或委托到一次绑定的父级 |
| 给现有 modal 写独立 close handler 而不走全局委托 | 多入口关一个忘了一个 | 全局 click handler + `data-close` 属性 |
| 鉴权用浏览器原生 `WWW-Authenticate: Basic` 弹窗 | 弹窗样式破坏终端实验室主题 | 走 cookie session(后端 `/api/auth/*` + 前端 `#auth-modal` 自定义 UI),详见 [deploy/auth-design.md](../deploy/auth-design.md) |
| 登录 form / 任何"必须看到才能继续"的 modal 走 Esc 关 | 用户 Esc 一下解锁所有内容 | 在 modal 上标 `data-no-esc`,`bindShortcuts` 跳过它 |
| API helper 不带 `credentials: 'same-origin'` | 跨主题前的 fetch 不发 cookie,永远 401 | 全局 `fetch('/api'..., { credentials: 'same-origin', ... })` |

---

## Required Patterns

| 模式 | 为什么必须 |
|------|-----------|
| **任何字符串拼进 HTML 必须过 `escapeHTML`** | 防 XSS,P1 后端 prompt / title / account name 都可能含 `<script>` |
| 所有 `<button>` / `<form>` 用真元素 + `type="button"` 或 `type="submit"` | 防止意外提交 form / a11y |
| 颜色必须用 `var(--*)` CSS variable | 主题切换才能生效 |
| 状态变化通过加 / 删 class,不操作 `element.style.*` | 见上;且 CSS 优先 |
| 异步 API 调用包 `try { ... } catch (e) { return alert('xxx失败: ' + e.message); }` | 否则失败时 UI 半截白屏 |
| 列表渲染用 `array.map(...).join('') \|\| '<空状态 HTML>'` | 空数组也有兜底 UI |
| 提交按钮点了立即 `btn.disabled = true`,失败再恢复 | 防止重复提交,见 `commitAccLogin` |
| 多入口可达的 modal 关闭走一个收口函数(`endAccLogin`),释放所有资源 | WebSocket / xterm / interval 不能漏 |
| 切 tab(`navigate()`)时关掉不属于当前 tab 的长连(`EventSource`) | 避免后台流持续耗流量 |
| 主题选择持久化到 `localStorage('vibebench-theme')`,并在 `<head>` 防 FOUC 内联脚本中先读 | 否则刷新时会出现"先暗后亮"的闪烁 |
| 中文注释解释 WHY(为什么这里 `try {} catch {}`、为什么这里加 setTimeout) | 全局指令 §3 |
| API helper 检测 401 → 自动 `showAuthModal()` + 抛 `'auth required'` Error | session 过期时任何调用都触发重登,无需每个 caller 自己写;`/api/auth/*` 自身豁免不递归弹框 |
| 启动时 `bootstrapAuth()` 探一次 `/api/auth/me`,401 时**只显示登录框,不调 navigate()** | 未登录就 navigate → 每个 render 都 401 → 一堆 alert 堆叠 |
| "粘贴一行 URL 自动填多个字段"模式(paste-helper) | 减少手填错;账号代理 URL 只支持 `http://` / `socks5://` / `socks5h://`,拒绝 `https://`;参考 `parseProxyUrl` / `applyProxyUrl` |

---

## Testing Requirements

**P1:无自动化测试**。**测试 = 真跑 + 浏览器点**。验收路径:

| 场景 | 验法 |
|------|------|
| 4 个 tab 切换 | 点导航 / 按 `1-4` / 改 hash → 视图正确切换 + 旧的 SSE 关掉 |
| 暗 / 明主题切换 | 点右上角 ☀/☾ → 颜色立刻切换 → 刷新仍保持 |
| 主题防 FOUC | 硬刷 / 系统首选浅色 → 第一帧就是正确主题,不闪暗 |
| 题库过滤 | `/` 聚焦 → 输入 → 实时过滤(title / category / 编号) |
| 添加账号两步流 | + 添加账号 → 填表 → start login → 看到 PTY 终端 → cancel / commit / 关 modal 三条路径都不漏资源(打开 devtools Network 看 ws 是否关、Application 看 session 是否清)|
| 创建任务 | 题库 → 卡片 → 选账号 + repeat → create → 跳到 tasks tab |
| 运行 + SSE | tasks ▶ run → 跳 runs → 看到状态从 queued → running → success,自动刷新无须人工 |
| 详情弹窗 | runs → detail → 看到 token 统计 / 文件树 / transcript |
| Esc 关 modal | 任意 modal 打开 → Esc → 关上 + 资源释放(对账号登录 modal 还要确认后端 session 取消) |
| 移动端 / 窄屏 | resize 浏览器到 ~720px → 表格 / topic 卡片不爆 |

**XSS 自测**:加一个名字含 `<img src=x onerror=alert(1)>` 的账号 / topic / prompt → 列表渲染**不应**弹 alert。

**P2 引入自动化测试时**:Playwright 跑黑盒,覆盖以上场景。

---

## Code Review Checklist

提交前自查 + Reviewer 必看:

- [ ] **XSS**:每个新写的 `innerHTML = ...` 里所有字符串变量是否过了 `escapeHTML`?
- [ ] **数字字段**:从 `FormData` 取出送给后端的字段是否用 `Number(...)` 显式转?
- [ ] **CSS variable**:新加的颜色 / 边框 / 字体都走 `var(--xxx)`?新主题 token 是否在 `:root` + `[data-theme=light]` 都定义?
- [ ] **无圆角 / 无 inline style**:新组件遵守终端皮肤约束?
- [ ] **资源释放**:新加的 `EventSource` / `WebSocket` / `setInterval` / `addEventListener` 是否在 modal 关闭 / 切 tab / endXXX 路径中显式释放?
- [ ] **`btn.disabled` 双向**:危险 / 不可重复提交按钮在点击时 disable、失败时恢复?
- [ ] **错误兜底**:`await API(...)` 全都包了 `try/catch`?失败有 `alert(...)` 或更友好提示?
- [ ] **空状态**:列表 render 是否带 `|| '<空状态 HTML>'`?
- [ ] **事件不叠加**:用了 `el.onclick = ...` 而不是 `addEventListener`?多次 render 后行为正常?
- [ ] **CDN 版本**:新引外部 CDN 包**带版本号**(`xterm@5.3.0` 而非 `xterm@latest`)?
- [ ] **a11y**:`<button>` 有 `aria-label`(图标按钮)?`<input>` 在 `<label>` 里?form 提交回车键能用?
- [ ] **快捷键**:新视图不影响 `Esc / / / 1-4`?新输入框是否在 `bindShortcuts` 的"in field 不响应"集合里(`INPUT/TEXTAREA/SELECT`)?
- [ ] **跨主题**:暗 / 明两种主题切到该视图都看起来正常?
- [ ] **后端契约**:新加的 API 路径 / 字段在 `orchestrator/main.py` 都对得上?字段名拼写一致?
- [ ] **console.log / debugger**:全部删掉?
- [ ] **中文注释**:复杂逻辑(为什么 sleep、为什么 try-catch、为什么这里 setState)说明 WHY?
