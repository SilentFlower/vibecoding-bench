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

async function endAccLogin({ alsoCloseModal = false, skipServerCancel = false } = {}) {
  const al = state.accLogin || {};
  // 此处仅展示收口顺序；启动/提交并发保护见下方 v3 场景和实际实现。
  if (al.sid && !skipServerCancel) {
    try { await API(`/accounts/login/${al.sid}`, { method: 'DELETE' }); }
    catch (error) { return; } // 结果未知时保留窗口、暂存和 state 供重试。
  }
  clearTimeout(al.pollTimer);
  al.connection?.dispose();
  state.accLogin = null;
  // ...UI 重置
}
```

**约定**:
- 句柄存到 `state.<feature>.<handle>`(`state.accLogin.ws` / `state.accLogin.term`)
- teardown 函数必须**幂等**:多次调用 / 资源已释放,都不能崩
- 本地句柄按幂等方式清理；服务端取消/凭据同步结果未知时不能吞错并丢掉维护资料。
- 服务端确认收口后 teardown **清空 state**(`state.accLogin = null`)；取消失败保留 state 和窗口，让用户重试。

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
- API 错误保留 `error.status`，便于生命周期区分鉴权/过期与可重试故障。
- 2xx → 返回 `json()` 结果

**不引入** SWR / React Query / 任何缓存层。**列表数据每次 render 重拉**,P1 数据量小够用。`state.topics` 是唯一带"已加载就复用"判断的(`if (state.topics.length === 0) { state.topics = await API('/topics'); }`),因为 seed 全量题(当前 600 道)通常只在题库维护后变化。

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

## Scenario: v3 登录终端重连与授权链接

### 1. Scope / Trigger

- 修改 `attachTerminal/attachAccLoginTerminal/startAccLogin/commitAccLogin/endAccLogin`、草稿列表、登录 modal、WS 票据或授权链接展示时适用。服务端提交见 [关联重授权](../backend/account-runtime-v3.md#scenario-v3-关联重授权提交与恢复)，草稿接口/私有记录/完整清理见 [未提交草稿](../backend/account-runtime-v3.md#scenario-v3-未提交登录草稿与完整清理)。

### 2. Signatures

```text
attachTerminal(hostSelector, wsPath, initialStatus='running', options={})
  -> Promise<{term,fit,ws getter,onResize,stop,reconnect,dispose}>
options: autoReconnect, startStopped, isActive, onSocket, onState
openLoginDraft(draft, action) -> Promise<void>；action=resume/restart
restartAccLogin() -> Promise<void>
GET /api/accounts/login/{sid}/status
POST /api/terminal-ticket {path: 原 WS 路径}
authorization_url(pane: str) -> str | None
```

### 3. Contracts

- v3 登录启用 autoReconnect，续聊默认不启用。重连只 attach 原 sid/tmux，每次取得新短票据；当前 socket 通过 getter/onSocket 更新，旧回调用 generation 与当前 state 校验。
- 重试延迟 1/2/4/8 秒、最多 8 次，连续稳定 30 秒才清重试数；心跳每 10 秒发送 ping，超过 30 秒无回包在下个 tick 关闭半开连接。手动重连不重启 CLI。Terminal/FitAddon 加载最多等 10 秒，窗口失效即停止。
- 只在当前窗口、当前 socket OPEN、输入获准时透传；离线输入丢弃并提示，不缓存/重放授权码。终态确定后，onData 和迟到的 WS.onerror 均不得覆盖结束原因。删除额外粘贴本地回显。服务端任一 pump 结束就取消另一 pump、关闭 attach；断线仅 detach。
- status 在窗口内每 2 秒串行查询，与 WS 首次输出独立；停止状态停止重连。取消期间暂缓轮询，取消失败继续查询；提交/关闭互斥。start HTTP 尚未取得 SID 时关闭窗口，标记 closeRequested，取得 SID 后确认取消再隐藏，避免后台遗留不可见登录。
- URL 来源为真实 CLI tmux pane：输入最多 65536 字符，剥 ANSI、最多拼 13 条连续 URL 字符硬换行，候选不超过 8192 字符；先拼完整 query 再校验，到续行上限仍有后续则拒绝有效前缀。仅接受 HTTPS 精确组合 `claude.com /cai/oauth/authorize`、`claude.ai /oauth/authorize`、`platform.claude.com /oauth/authorize`，无 fragment，PKCE 必需参数单一非空、code/S256、43 字符 base64url challenge/state；redirect 主机为 platform.claude.com 或 console.anthropic.com 的 HTTPS。不生成或补猜参数；CLI 升级须核对实际形状，不能把白名单主机/路径交叉组合。
- URL 以 textarea.value/textContent 展示；打开用 `_blank`、`noopener,noreferrer`。复制依次尝试安全 Clipboard、选中完整文本的 execCommand，再明确手动复制；未复制不报成功。URL 不进入持久缓存或日志。
- 会话过期、鉴权失效或进入提交阶段后停止重连/心跳与终端输入，status 停止条件也终止轮询；终端和窗口留供显示诊断。关闭、成功提交或确认取消后释放 socket、xterm、输入订阅及 resize listener，并清 state；取消失败保窗。窄屏终端区域要能滚动，提交/取消按钮必须实际可点击；同步静态资源版本与明暗主题。
- v3 status 200 可返回 ended、message 和 restartable，不能继续显示普通断线提示；重新连接仅用于活跃原 SID，重新登录才生成新 SID。ready_to_submit 已经通过服务端认证检查，可停止终端后提交；恢复窗口用 startStopped 避免连接不存在的 tmux。
- 账号页将草稿作为独立行展示，`state.accounts` 和正式任务下拉不混入草稿。所有动作传页面 generation，操作许可来自 DTO；删除确认说明未提交授权产物也将清除，失败刷新可见状态。启动与恢复期间关窗仍等待 SID，再确认取消；清理未知不丢 state。

### 4. Validation & Error Matrix

| 条件 | 页面行为 |
|---|---|
| 普通断线/短期网络故障 | 有界重试或手动重连原会话，取新票据 |
| status 200 + ended | 停止连接/输入/轮询，保留 message，显示重新登录；迟到错误不覆盖 |
| ready_to_submit / 恢复产物窗口 | 终端停止，显示认证已通过，允许提交保存 |
| status 401/403/404/409/410 | 停止连接/轮询，清链接，显示结束/失效状态 |
| WS 4004/4401/4404 | 停止重连和输入，显示结束/鉴权失效；链接是否有效继续由 status 判断 |
| submitting/committed | 禁止继续向终端输入，提示重试/对账或完成 |
| 非官方/非 HTTPS/截断/重复参数/超长 URL | 不展示无效候选，保留终端手动流程 |
| HTTP 或复制权限不支持 | 选择完整 URL，明确手动复制 |
| 服务端取消失败/结果未知 | 保留窗口和 state，不假报关闭成功 |
| 草稿 preparing/deleting/submitting/reconcile 或代次冲突 | 按许可禁用动作或显示错误并刷新，不操作正式账号资源 |

### 5. Scenarios and Examples

- 正常：终端已输出 URL 后断线，HTTP 仍读原 pane；自动或手动重连取新 ticket，原 sid 不变。
- 基础：HTTP 非安全上下文没有 Clipboard，选中可复制；390px 明暗主题能滚动并点击提交。
- 基础：刷新账号页发现草稿，继续原 SID；管理器重启后按服务端返回的中断/认证状态选择重登或提交，不伪造原终端。
- 错误用法：保存 ticket URL 反复重连，或离线缓存输入后补发。正确处理：新建连接代次、重新出票、丢弃离线输入。
- 错误用法：调用 DELETE 后立即清 state、吞掉失败。正确处理：await 服务端确认，保留失败窗口；启动中关闭也等 SID 收口。
- 错误用法：CLI 已退出后仍让输入或迟到 onerror 把原因改成等待重连。正确处理：stop 后所有连接/输入回调尊重终态，另提供明确重新登录。

### 6. Tests Required

- URL 单测覆盖三个精确入口、拒绝交叉路径、ANSI、软/硬换行、续行上限、截断 state、换行后的重复参数、恶意主机/fragment、非 HTTPS；取真实支持 CLI 的脱敏形状核对，不只用自造样本。
- 真实 Chrome 验证断线与手动重连的新票据/同 sid、离线输入未到 tmux、启动中关闭、HTTP 复制选择、打开参数、1280/390 明暗和真实点击；打开外页在测试中拦截，不能访问真实 OAuth。
- 取消/过期/退出与非法票据、半开 pump 收口；旧未绑定登录/续聊默认行为回归。`node --check webui/app.js`，组件/错误路径变动后复用对应隔离验证。
- 草稿真实浏览器验证刷新继续、CLI 退出后离线输入及人工迟到 onerror 不覆盖结束原因、原环境重登、宕机后产物恢复、提交和删除按钮实际鼠标点击；坏元数据的只读状态与正式账号可用性由对应 SQLite/API 回归证明。
