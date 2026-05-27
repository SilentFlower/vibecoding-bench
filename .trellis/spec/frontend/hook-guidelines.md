# Hook Guidelines

> 本项目无 React,本文件描述本项目对应"自定义 hook"的等价物。

---

## Overview

**本项目不用 React / Vue / 任何带 hooks 概念的框架**,因此严格意义上没有"hook"。模板里这个文件保留下来,是为了说明:**当出现"在多处复用的有状态逻辑"时**,本项目用什么方式组织。

等价物分两类:

1. **生命周期型副作用**(挂监听、起 interval、订阅 SSE)→ 写成**初始化函数 + 收口函数对**,把句柄存到 `state.<feature>.<handle>`
2. **数据获取**(从 `/api/...` 取数据)→ 不抽 hook,直接在 render 函数里 `await API(path)`,失败 `alert + return`

P1 阶段**故意不抽抽象**:复用度 ≥3 处再考虑抽函数;<3 处时,inline 写最直接。

---

## Custom Hook Patterns

无框架,但有几类**复用的"有副作用初始化"函数**,统一长这样:

```js
function setup<Thing>() {
  const el = document.getElementById('<id>');
  if (!el) return;           // 元素不存在直接 noop,允许在没有该 UI 的页里调用
  // 1. 初始化(读取持久化、设默认值)
  // 2. 绑事件 / 起 interval / 订 EventSource
  // 3. (可选)把句柄挂到全局可清的地方
}
```

实际实例:

- `setupTheme()`:读 `localStorage('vibebench-theme')` → 设 `<html data-theme>` → 绑 toggle 按钮点击
- `startClock()`:定时刷新 `#clock` 文本(每秒一次)
- `bindShortcuts()`:全局 keydown 监听,处理 Esc / `/` / `1-4`

调用时机:`app.js` 末尾**只调一次**:

```js
navigate();         // 路由首次渲染
setupTheme();
startClock();
bindShortcuts();
```

### 需要"清理"的有状态副作用 —— 用 setup/teardown 对

如 OAuth 登录第二步的 PTY 桥,挂的资源很多(WebSocket / xterm 实例 / window resize listener / 后端 session):

```js
async function attachAccLoginTerminal(wsPath) {
  // ...创建 term / ws / 绑事件 / addEventListener('resize', onResize)
  state.accLogin.term = term;
  state.accLogin.fit = fit;
  state.accLogin.ws = ws;
  state.accLogin.onResize = onResize;
}

function endAccLogin({ alsoCloseModal = false, skipServerCancel = false } = {}) {
  const al = state.accLogin || {};
  if (al.ws && al.ws.readyState <= 1) { try { al.ws.close(); } catch {} }
  if (al.term) { try { al.term.dispose(); } catch {} }
  if (al.onResize) window.removeEventListener('resize', al.onResize);
  if (al.sid && !skipServerCancel) API(`/accounts/login/${al.sid}`, { method: 'DELETE' }).catch(() => {});
  state.accLogin = null;
  // ...UI 重置
}
```

**约定**:
- 句柄存到 `state.<feature>.<handle>`(`state.accLogin.ws` / `state.accLogin.term`)
- teardown 函数必须**幂等**:多次调用 / 资源已释放,都不能崩
- 所有清理操作包 `try {} catch {}`,清理失败不要妨碍后续清理
- teardown 必须**清空 state**(`state.accLogin = null`),防止悬挂引用

---

## Data Fetching

**不抽 hook**。模式:

```js
async function renderX() {
  try {
    state.x = await API('/x');                    // 单源
    // 或并行:
    // [state.x, state.y] = await Promise.all([API('/x'), API('/y')]);
  } catch (e) {
    return alert('加载失败: ' + e.message);
  }
  // ...渲染
}
```

`API()` 已统一处理:
- `Content-Type: application/json`
- 非 2xx → 抛 `Error(detail || statusText)`
- 2xx → 返回 `json()` 结果

**不引入** SWR / React Query / 任何缓存层。**列表数据每次 render 重拉**,P1 数据量小够用。`state.topics` 是唯一带"已加载就复用"判断的(`if (state.topics.length === 0) { state.topics = await API('/topics'); }`),因为 200 道题通常只在题库维护后变化。

### SSE / WebSocket

不抽 hook,直接在 render 函数里 `new EventSource(...)` / `new WebSocket(...)`,把句柄存到 `state.<feature>EventSource` / `state.<feature>.ws`,切 tab / 关 modal 时收口关掉(看 `navigate()` 里 `if (tab !== 'runs' && state.runsEventSource) { ... }`)。

---

## Naming Conventions

由于不是 React,**禁止 `use<X>` 前缀**(会误导)。命名约定:

| 角色 | 前缀 | 例子 |
|------|------|------|
| 初始化(一次性,无清理需求) | `setup<X>` / `start<X>` / `bind<X>` | `setupTheme / startClock / bindShortcuts` |
| 副作用挂载(有对应清理) | `attach<X>` | `attachAccLoginTerminal` |
| 副作用收口 | `end<X>` / `cleanup<X>` / `detach<X>` | `endAccLogin` |
| 视图渲染 | `render<Tab>` | `renderAccounts / renderTopics / renderTasks / renderRuns` |
| 重绘已有视图 | `paint<X>` | `paintRuns`(SSE 帧到达时只重绘 body,不重拉数据) |
| 弹窗 open | `open<X>Modal` | `openTaskModal / openRunDetail / openAccLoginModal` |
| 弹窗工具 | `openModal / closeModal` | 通用 toggle `.hidden` |
| API 调用 | `API(path, opts)` | 全项目唯一入口 |
| DOM 简写 | `$ / $$` | querySelector / querySelectorAll |

---

## Common Mistakes

| 反模式 | 为什么不要 | 怎么改 |
|--------|------------|--------|
| 在没有 React 的项目里写 `useFoo()` 命名 | 让人以为有 hooks,实际只是普通函数 | 用 `setupFoo / startFoo / bindFoo` |
| 抽出一个"通用 fetcher hook" | 没有依赖追踪 / 没有缓存,只是 `await fetch` 包装,纯噪音 | 直接 `await API('/x')` |
| 把句柄挂 `window.<x>` 而不是 `state.<x>` | `window` 是浏览器全局,会和别人冲突;且 teardown 不易统一 | 永远存进 `state.<feature>` |
| 起 `setInterval` 不存 id / 不在切页时清 | 切页后定时器还在,触发 noop 或报错 | 存到 `state.<feature>.intervalId`,切页时 `clearInterval` |
| EventSource / WebSocket 重复 `new` 不关旧的 | 同时多条流,流量翻倍且事件叠加 | render 函数开头先 `if (state.<x>EventSource) state.<x>EventSource.close()` |
| `setup` 函数依赖 DOM 元素存在但不防御 `if (!el) return` | 在不挂该 UI 的页面调用时 `el.onclick` 抛 TypeError | 所有 setup 头部都加防御 |
| 清理路径不 `try/catch` | 一个资源已经被关 / 抛异常 → 后续资源没机会清 | 每个清理动作单独 `try {} catch {}` |
| 数据加载不显示 loading 状态 | 用户以为卡死 | render 入口可立即 `body.innerHTML = '<tr><td>加载中…</td></tr>'`,await 完再覆写 |
