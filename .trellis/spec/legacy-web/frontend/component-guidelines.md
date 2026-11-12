# Component Guidelines

> 本项目"组件"的写法 —— 无框架版。

---

## Overview

**本项目没有组件框架**(无 React / Vue / Svelte / lit-html)。这里的"组件"是指**逻辑上独立的 UI 块**,有以下几种表现:

1. **视图组件**(整页) → `<template id="tpl-<tab>">` + `render<Tab>()` 函数对
2. **弹窗组件**(modal) → `<div class="modal hidden" id="<feature>-modal">` + 一组 open/close 函数
3. **行 / 卡片组件**(列表元素) → render 函数里的模板字符串
4. **状态徽章 / 按钮**(原子) → 直接写 class,无函数封装

整体哲学:**HTML 写结构、CSS 写样式、JS 写数据 → DOM 注入**。每次 render 整段 `innerHTML = ...` 覆写,**不做 diff、不做虚拟 DOM**,所以渲染必须够快(P1 数据量小,无问题)。

---

## Component Structure

### 视图组件(整页 tab)

**模板部分**(`index.html`):

```html
<template id="tpl-tasks">
  <section class="view">
    <header class="view-head">
      <div>
        <h2 class="view-title"><span class="bracket">▌</span>tasks <span class="muted">// dispatched</span></h2>
        <p class="hint">点 <code>▶ run</code> 按 <code>repeat_n</code> 提交多次运行,每账号同时最多 2 个。</p>
      </div>
    </header>
    <div class="table-frame">
      <table class="data">
        <thead><tr>
          <th>id</th><th>no</th><th>title</th><th>account</th>
          <th class="right">repeat</th><th class="right">timeout</th><th>op</th>
        </tr></thead>
        <tbody id="tasks-body"></tbody>
      </table>
    </div>
  </section>
</template>
```

**逻辑部分**(`app.js`):

```js
async function renderTasks() {
  try {
    state.tasks = await API('/tasks');
    state.accounts = await API('/accounts');
  } catch (e) { return alert('加载任务失败: ' + e.message); }

  const accMap = Object.fromEntries(state.accounts.map(a => [a.id, a.name]));
  const body = $('#tasks-body');
  body.innerHTML = state.tasks.map(t => `
    <tr>
      <td>${t.id}</td>
      <td>#${t.topic_no}</td>
      <td>${escapeHTML(t.title)}</td>
      <td>${escapeHTML(accMap[t.account_id] || `acc#${t.account_id}`)}</td>
      ...
    </tr>
  `).join('') || '<tr><td colspan="7" class="muted" ...>暂无任务...</td></tr>';

  body.onclick = async (e) => { ... };
}
```

**视图组件的标准结构**(每个 `render<Tab>()` 都必须有):
1. 拉数据(放进 `state.<feature>`)→ 失败 `alert + return`
2. 计算派生数据(查表、过滤)
3. 拼 HTML(`array.map(...).join('') || '空状态 HTML'`)
4. `innerHTML = ...` 覆写
5. 绑事件(`element.onclick = ...`,**单 handler 覆盖式**,避免重复 render 时叠加)

> `navigate()` 已经把 `<template>` clone 进 `#view`,**所以 render 函数永远能拿到 `#tasks-body` 这种元素**,不要自己再 clone template。

### 弹窗组件(modal)

模板写在 `index.html` 末尾,默认带 `.hidden`:

```html
<div class="modal hidden" id="task-modal">
  <div class="modal-card modal-card-sm">
    <div class="modal-frame" aria-hidden="true">
      <span class="frame-tl">┌</span><span class="frame-tr">┐</span>
      <span class="frame-bl">└</span><span class="frame-br">┘</span>
    </div>
    <div class="modal-titlebar">
      <span class="modal-titlebar-name">task / new <span class="muted" id="task-modal-title"></span></span>
      <button class="modal-close" data-close="#task-modal" aria-label="close">×</button>
    </div>
    <form id="task-form" class="form">...</form>
  </div>
</div>
```

打开 / 关闭通过 helper:`openModal('#task-modal')` / `closeModal('#task-modal')`,内部只是 toggle `.hidden`。

**关闭路径必须收口**(看 `endAccLogin`):
- 关 modal 之前要释放它持有的资源(WebSocket、xterm、resize listener、后端 session)
- 多入口关(close 按钮 / 点遮罩 / Esc / commit 成功后)都走同一个收口函数

模板里 `data-close="#xxx"` 让全局点击委托 handler(`document.addEventListener('click', ...)`)统一关弹窗,**不要自己再绑独立 close handler**。

### 行 / 卡片组件

列表项**不抽函数**,直接在 render 里写模板字符串。当模板字符串超过 ~15 行或被多处复用时再抽:

```js
// 抽函数时的命名:render<Item>(it) 返回 HTML 字符串
function renderTopicCard(t) {
  return `
    <div class="topic-card" data-no="${t.no}">
      <div class="topic-no">#${t.no}</div>
      ...
    </div>
  `;
}
```

---

## Props Conventions

无组件框架 → 无 props 概念。**等价物**:

| 场景 | 怎么传 |
|------|--------|
| render 函数依赖外部数据 | 全部从 `state.*` 读,**不要新增函数参数**(每个 render 入口应当能被 `navigate()` 零参调用) |
| modal 需要知道"展开哪一项" | 通过 open 函数参数传:`openTaskModal(topicNo)` / `openRunDetail(rid)` |
| 列表项 → 行内按钮回调 | 用 `data-<action>="<id>"`,在 `body.onclick` 事件委托里 `e.target.dataset.<action>` 取出 |

**禁止**:
- 用 `window.<something> = ...` 在组件间传数据,统一走 `state`
- 把"配置"硬编码进 HTML(如颜色、阈值),应在 CSS variable / JS 常量里

---

## Styling Patterns

**所有样式集中在 `apps/legacy-web/style.css`**,**不写 inline `style="..."` 属性**(全文极少例外:`tlab` 系列 `style="text-align:center;padding:24px"` 是空状态行,日后应抽成 class `.empty-row`)。

### 主题 / 状态全部通过 CSS variable

不要在 JS 里改颜色。状态变化通过**改 class**:

```js
// ✓ 正确
elem.classList.add('pill-running');     // CSS 里 .pill-running { color: var(--running); ... }

// ✗ 错误
elem.style.color = '#5fd7d7';
```

主题切换只需要改 `<html data-theme="light|dark">`,所有 `var(--xxx)` 自动跟随。

### class 命名(从代码现状归纳)

| 类型 | 模式 | 例子 |
|------|------|------|
| 视图布局 | `.view / .view-head / .view-title / .hint` | 每个 tab 顶部都有 |
| 表格 | `.table-frame / table.data / .right`(右对齐数字列) | accounts / tasks / runs 三个 tab 共用 |
| 按钮 | `.btn / .btn-primary / .btn-danger / .btn-sm` | 大小:默认 / sm;变体:default / primary / danger |
| 状态徽章 | `.pill / .pill-<status>` | `pill-queued / pill-running / pill-success / pill-failed / pill-timeout` |
| 表单 | `.form / .lbl / .row / .row-end / .hint.inline` | acc-form / task-form |
| modal | `.modal / .modal-card / .modal-card-sm / .modal-card-md / .modal-titlebar / .modal-frame / .modal-close` | 弹窗框 |
| 终端饰物 | `.bracket(▌)`、`.prompt($)`、`.caret(_)`、`.scanlines`、`.frame-tl/tr/bl/br(┌┐└┘)` | 终端实验室皮肤元素,不要乱用 |
| 详情面板 | `.detail-section / .stats-grid / .stat-box / .stat-label / .stat-value / .file-tree` | run 详情弹窗 |
| 辅助 | `.muted / .hidden` | 弱化文字 / 隐藏元素 |

### 终端皮肤硬约束

本段适用于终端皮肤页面。环境路由使用文末环境页场景规定的主后台视觉作用域，保留其它页面的原主题。

- 全局 `border-radius: 0 !important`,**任何新组件都不要圆角**
- 颜色必须用 CSS variable,**不写 hex 字面量**(`<input type="color">` 除外)
- 状态色(`--running` 等)在皮肤上有 `*-glow` 阴影变体,运行中元素带 `box-shadow: 0 0 X var(--running-glow)`
- 等宽字体优先(`var(--mono)`),只有 banner / 大标题用 `var(--display)`

---

## Accessibility

P1 阶段做到的:

- 所有 `<button>` 用真 `<button type="button">` 或 `type="submit">`,**不用 `<div onclick>` 模拟**
- 关键交互按钮带 `aria-label`(`#theme-toggle / #modal-close / #acc-modal-close`)
- modal 框架元素带 `aria-hidden="true"`(`.modal-frame / .scanlines / .hintbar`)
- 表单 `<input>` 都有外层 `<label>`(`<label><span class="lbl">$ name</span><input .../></label>`)
- Esc 关 modal(`bindShortcuts` 里实现)
- 焦点不被偷:输入框聚焦时,数字快捷键 `1-4` 不切 tab(`if (inField) return;`)

**未做 / 待补**:
- 没有 focus trap(modal 打开后 Tab 仍可跳出 modal)
- 没有 `aria-live` 区域宣告 SSE 状态变化
- 没有跳过导航的 skip link
- 色对比度仅按视觉调,未跑 WCAG 工具

新增组件时优先用语义元素(`<section>` / `<header>` / `<table>` / `<nav>`),不要全用 `<div>`。

---

## Common Mistakes

| 反模式 | 为什么不要 | 怎么改 |
|--------|------------|--------|
| `body.innerHTML += '<tr>...'` | 每次拼接重建整个 tbody,丢失事件;且和 `.map().join('')` 思路冲突 | 一次性 `innerHTML = state.<list>.map(...).join('')` |
| 把用户输入直接拼进模板字符串 | XSS(account name / prompt / title 全可被攻击) | **永远** `escapeHTML(value)` 包一层 |
| 模板里嵌入复杂逻辑(三元嵌套 + JSON.stringify 嵌套) | 不可读 | 把分支抽成函数 / 局部常量,再拼字符串 |
| 用 `addEventListener('click', ...)` 在每次 render 重复绑 | 会叠加 handler,触发 N 倍 | 用 `element.onclick = ...` 覆盖式赋值;或事件委托到一次绑定的父元素 |
| 用 `data-toggle="modal"` 之类 Bootstrap 风格属性 | 没引 Bootstrap,只会让人困惑 | 显式 `openModal('#xxx')` / `closeModal('#xxx')` |
| 在 render 函数里 `await fetch` 但忘了 `try/catch` | 失败时 UI 半截白屏,没有提示 | render 函数顶部 `try { ... } catch (e) { return alert('xxx: ' + e.message); }` |
| 用全局 `setTimeout` 轮询替代 SSE | 浪费请求 + 状态可能错过 | runs 必须用 `/api/runs/stream`(SSE),前端 `EventSource` |
| modal 关闭时不清异步资源(WebSocket、setInterval、EventSource) | 资源泄漏,关一次累积一份 | 关闭路径走收口函数,显式 `ws.close()` / `clearInterval(...)` |
| 给一个 modal 写多个独立 close handler | 出新入口忘了一处就泄漏 | 全局点击委托 + 收口函数 |
| 触发删除 / 危险动作不二次确认 | 误删账号 | 用 `confirm('删除账号 #' + id + '?')`,看 `renderAccounts` 的范式 |

## Scenario: 环境页与主后台视觉一致性及内核弹窗

### 1. Scope / Trigger

- 修改 `#environments`、`apps/legacy-web/environments.js`、`apps/legacy-web/environments.css` 或内核弹窗时适用。
- 本页保持零构建与原生 JS，通过 gateway 的统一会话嵌入；其它业务页继续使用终端主题。

### 2. Signatures

- `renderEnvironments(): Promise<void>` 读取 `/api/environments`；`paintEnvironments(): void` 仅重绘列表。
- `openNativeKernelDialog(button): void`、`submitNativeKernel(event): Promise<void>`、`closeNativeKernelDialog(force=false): boolean` 管理内核表单；`leaveEnvironments(): void` 收口页面资源。
- 内核仍使用 `POST /api/environments/{environment_id}/native-kernel`，字段为 `operation`、`operation_id`、`release`、`expected_sha256`、`expected_revision`。服务端状态与准入以 [运行环境合同](../../orchestrator/backend/account-runtime-v3.md) 的单账号内核场景为准。
- `openRunWindowConfig(aid)` 在打开窗口时绑定共享表单，直接进入环境页也能操作原时段配置。

### 3. Contracts

- `:root.environment-page` 使用主后台中性亮色、绿色强调色与正文层级；只有该作用域可覆盖旧直角 reset、扫描线、内层导航与弹窗。保留 `data-theme` 和 `vibebench-theme` 原值，离开环境路由移除作用域后恢复原页面主题。作用域选择器需与旧 `:root[data-theme=light]` 具有足够优先级。
- `index.html` 按 `projects.js`、`environments.js`、`app.js` 装载。环境模块仅定义函数及常量，实际调用继续使用 `app.js` 的 API/state；资源修改同步静态版本参数。
- `state.environmentUI` 保存服务器 rows、搜索、筛选、展开集合、操作中集合、只读请求序号及定时器。搜索筛选只派生当前 rows，不发送写请求；详情按环境 ID 和区块恢复。
- 列表读取同时检查 `viewGeneration` 与请求序号，旧页面或旧请求结果不得覆盖新视图。工具栏与弹窗位于列表重绘区外，输入、光标和焦点不被进度刷新重置。
- 内核状态只读 `native_kernel`。null 显示当前未提供管理，未知状态保留可见提示并禁用普通动作；候选缺失或与当前摘要一致时禁用激活，CLI 忙碌与本地操作中时阻止重复提交，待对账仅提供对应恢复入口。
- 原生准备区只读 `native_preparation`，与历史内核预热回执分开展示；字段投影见[原生 sender 合同](../../orchestrator/backend/account-runtime-v3.md#scenario-v3-原生-sender-共享映像池与资源预算)。显示当前状态、空闲/物理进程数、PID、检查时间和白名单原因，缺证据显示未知。存在原生准备摘要时每20秒串行刷新，操作中的2秒轮询优先；复用原请求序号、页面归属及离页清理。
- 准备表单使用发布标签 `v0.1.0-beta.[1-9][0-9]{0,8}`；激活和回滚确认显示账号、当前版本与目标版本。打开窗口时冻结 revision、release 和摘要；列表刷新不得替换该上下文。写入只由用户提交触发，每次使用独立操作 ID，失败或冲突不自动重放。
- 进度轮询为操作期间每两秒的串行 GET。离页清理定时器并使窗口归属失效；已经发出的服务端操作仍由原所有者收口，迟到回包不重开窗口。普通提交中关窗保持等待，导航强制关闭只使本地回调失效。
- 关闭按钮、遮罩与 Esc 统一走 `closeModal` 及内核窗口收口。窗口提供可见焦点与 Tab 边界；取消尚未提交的表单保持零写入。原运行窗口、实测、交接与维护入口继续沿用现有接口和服务器许可。

### 4. Validation & Error Matrix

| 条件 | 页面行为 |
| --- | --- |
| 列表读取失败 | 展示错误；已有快照时明确为上次读取结果 |
| 服务器返回未知环境状态 | 显示原状态并可筛选，不静默解释为就绪 |
| 内核字段缺失、候选缺失或 CLI 忙碌 | 显示缺口或忙碌，禁用相应动作 |
| 409 或内核操作失败 | 原窗口显示错误，要求关闭并刷新后重新操作 |
| 重复点击、轮询或取消 | 不增加非预期写入；取消不提交操作 |
| 切页及乱序 HTTP 回包 | 清理旧定时器/窗口，丢弃过期页面或列表结果 |
| 原生准备失败、过期或准备中 | 展示相应状态与最近检查，刷新保持只读 |

### 5. Scenarios and Examples

- 正常：环境页准备候选 → 激活确认 → 读取实际当前版本 → 回滚确认；完整摘要与预热回执在详情展示。
- 边界：390px 展开长 ID、完整摘要与物理实测，页面保持可读；保留未采集和未限制的不同口径。
- 错误用法：每两秒重建整个 view 并重填确认窗口的新 revision。正确方式：只更新列表，确认请求保持用户打开窗口时看到的版本。
- 错误用法：用全局圆角和色板覆盖其它页面。正确方式：环境路由设置作用域，离页恢复原主题偏好。
- 正常：原生环境显示暖进程 PID 与检查时间；错误用法：把内核历史准备成功显示为实时就绪。正确方式：读取独立 `native_preparation` 摘要。

### 6. Tests Required

- `node --check apps/legacy-web/app.js`、`node --check apps/legacy-web/environments.js`、`node --check apps/legacy-web/projects.js`。
- 在已有 Playwright 和 gateway `web/dist` 的本地环境运行 `python3 deploy/v3/verify_environment_ui.py --output .deploy/environment-ui-verification`。缺少 gateway 静态产物时先执行 `cd services/gateway/web && npm run build`。
- 合成浏览器须覆盖实际 gateway 导航和 iframe、1280/720/390px 及原明暗偏好、真实按钮操作、版本冲突、提交去重、取消、轮询编辑、乱序回包、切页清理、长字段、空列表、错误文本转义及原运行窗口/物理实测入口。
- 断言进入页面没有业务写入，主动操作 payload 保持既有合同，所有请求使用合成接口；实际账号、OAuth 与模型调用不作为本地 UI 验收前提。
- 准备状态回归覆盖 ready/preparing/failed/过期、390px、定时刷新归属及零写入；请求诊断合成场景同时核验实际暖命中、PID、重叠计时与历史未观测。
