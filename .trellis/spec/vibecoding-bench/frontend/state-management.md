# State Management

> 本项目的状态管理 —— 单 `state` 对象 + 直接赋值。

---

## Overview

**本项目不用任何状态管理库**(无 Redux / MobX / Zustand / Pinia / Recoil)。

唯一的全局状态是 `app.js` 顶部的一个 plain object:

```js
const state = {
  accounts: [],
  topics: [],
  tasks: [],
  runs: [],
  topicFilter: '',
  runsEventSource: null,
};
```

需要时其他 feature 直接附加属性(如 OAuth 登录两步流期间挂 `state.accLogin = { sid, ws, term, fit, onResize, body, name }`)。

**理由**:
- 项目只有 4 个 tab,数据规模和交互复杂度都很小
- SSE 是唯一长连,其他都是请求-响应
- 没有路由层级共享 / context 传递的需求
- "可订阅 / reactive" 的需求不存在 —— 用户操作都是显式触发 render,SSE 显式触发 paint

---

## State Categories

| 类别 | 在哪 | 例子 |
|------|------|------|
| **服务端数据(列表缓存)** | `state.<resource>` | `state.accounts / state.topics / state.tasks / state.runs` |
| **UI 临时态** | `state.<feature>` | `state.topicFilter`(搜索框文字)、`state.accLogin`(登录两步流上下文) |
| **副作用句柄** | `state.<feature>(EventSource\|.ws\|.term\|...)` | `state.runsEventSource`、`state.accLogin.ws` 等 |
| **路由状态** | URL hash | `location.hash`(`#accounts / #topics / #tasks / #runs`),不复制到 `state` |
| **持久化偏好** | `localStorage` | `vibebench-theme` 主题选择;不复制到 `state`,每次读 |
| **数据派生** | 局部变量 | render 内 `const accMap = Object.fromEntries(state.accounts.map(a => [a.id, a.name]))`;**不缓存进 state** |

**禁止**:
- 把 URL 路由复制成 `state.currentTab`(`currentTab()` 函数每次读 hash,单一来源)
- 把 localStorage 复制进 `state`(双向同步是 bug 之源,直接读)
- 把派生数据存进 `state`(`accMap` 这种映射在 render 时一次性算出来即可)

---

## When to Use Global State

**判定标准**(只要满足任一条就放 `state`):

1. **跨 tab 复用**:`accounts` 在 accounts / tasks / runs 三个 tab 都要用 → 全局
2. **SSE 推送后异步覆盖**:`runs` 由 `/api/runs/stream` 异步覆盖 + UI 也读 → 全局
3. **跨函数寿命**:OAuth 两步流的 ws / term 由 `attachAccLoginTerminal` 创建、由 `endAccLogin` 释放 → 全局
4. **持久化 / 长寿命缓存**:`topics`(seed 全量题,当前 600 道,一次加载后基本不变)→ 全局

**其余一律用局部变量**:render 内的中间计算、modal 内的 form 数据、单次按钮点击的临时数据。

新增 feature 时,**默认不加 `state.<x>`**,先用局部变量写;真撞到上面四条之一,再升到全局。

---

## Scenario: 工程迭代空间与账号 URL 状态

### 1. Scope / Trigger

- 修改工程迭代入口、ProjectsUI 的挂载/选择、空间切换或订阅生命周期时适用。顶层只有“工程迭代”，页内为“项目迭代 / 养号迭代”；不合并后台空间。

### 2. Signatures

```text
#projects?account=<id>
#warmup?account=<id>
iterationAccount() -> number | null
iterationUrl(mode, accountId) -> string
ProjectsUI.mount({api, prefix, namespace, accountId, configureCli, showCapture, closePanels, onAccountChange})
ProjectsUI.unmount()
onAccountChange(accountId: number | null) -> void
```

### 3. Contracts

- hash 页面名与查询参数分别解析。两个模式激活同一个顶层入口；统一入口默认 #projects。原 #projects/#warmup 无参链接继续沿用有效已配置账号的原默认规则。
- account 仅接受一个正安全整数；重复、负数、文本、额外问号混入值及超安全范围返回内部哨兵 0，无参返回 null。显式无效/停用/删除账号保持未选择并提示，不自动换号；主动清空选择也通过 account=0 保留未选状态。
- URL 是模式/账号的唯一持久来源，不再保存一次性 warmupAccountId 或 localStorage/currentTab 镜像。账号改变通过 history.replaceState 更新当前条目及页内链接，不重挂载；切空间使用正常 hash 导航，刷新、前进后退恢复当前选择。账号页直达养号使用带 account 的 #warmup 地址。
- mount 固定 namespace 和 endpoint：projects 对应 /projects，warmup 对应 /accounts/warmup/pi。选择回调仅在本次 viewGeneration/模式仍有效时更新 URL。导航不保存表单、不配置/启动/暂停/停止工作，不复制计划或历史；只有明确操作按钮才能发业务写请求。
- 切换前 unmount 先使 revision/selection 失效，关闭 SSE、时钟和配置/抓包窗口，清空分页。旧 HTTP/SSE 回包不得写入新空间；只保留当前空间的一个 SSE 和一个页面时钟。两个后台空间及其执行、工作区、会话与事实保持独立。
- 页内使用原生链接、aria-current 与 focus-visible，Enter 可操作；保留终端/交互记录内页签。顶层数字快捷键和页脚同步为 1–6；主题颜色使用既有变量，修改 app/projects/CSS 时同步 index.html 的资源版本。

### 4. Validation & Error Matrix

| 条件 | 页面结果 |
| --- | --- |
| 旧无参链接 | 沿原规则默认选择；实际选中后补 URL |
| 明确有效账号 | 两空间往返、刷新及历史恢复同账号 |
| 无效、重复或不可用账号 | 未选择并提示“该账号当前不可用”，不静默换号 |
| 旧请求晚于切页返回 | 代次不符，丢弃旧响应 |
| 切空间或离开页面 | 旧 SSE/时钟/弹窗释放，后台工作不启停 |

### 5. Scenarios and Examples

- 正常：#projects?account=7 → 点击养号 → #warmup?account=7，刷新仍为养号 7；返回后恢复项目 7。
- 基础：首次访问 #projects 沿原默认规则；在选择框改成账号 9，replaceState 记录 9，不重建当前订阅页面。
- 错误用法：账号 7 已被停用，自动退回账号 9，或把旧项目响应写入养号 DOM。正确处理：保持未选择并要求重选；按 revision/selection 丢弃旧回包。

### 6. Tests Required

- node --check webui/app.js、webui/projects.js；真实浏览器入口为 verify_stack.py --manifest <联合清单> --browser --project-iteration。
- Chrome + HTTP + SQLite + SSE：单一顶层入口、Enter 键、账号 A/B、实际新 Document 刷新、浏览历史、旧链接与账号页直达；非法/重复/停用/删除账号不换号。
- 两空间配置/计划/终端/记录/分页分别读取；导航阶段只有 GET，前后持久业务表一致。延迟旧快照并连续切换20次，最多一个当前 SSE、时钟不累积，卸载全部释放。
- CLI 配置与工作抓包路径按本空间，切换关闭旧窗口；1280/720/390px 明暗主题无横向溢出。合成持久工作保持不等于真实模型已执行，部署后另核对现有工作事实。

## Server State

**不引入** SWR / React Query / 任何"server state"框架。约定:

| 场景 | 策略 |
|------|------|
| 列表数据(account / task / run) | 每次进 tab 时**重新拉** `await API('/...')`,覆盖 `state.<x>`。**不做客户端缓存有效期判定** |
| 静态数据(topics 300 题) | 第一次拉了缓存到 `state.topics`,后续 `if (state.topics.length === 0) await API('/topics')` |
| 实时数据(runs) | SSE `/api/runs/stream` 推全量,前端无差量;且**首次进页同时拉一次 `/api/runs`** 兜底首屏(SSE 第一帧到达可能要 1 秒) |
| 写操作后刷新 | 写完(`POST /api/...` 成功)显式调对应 `render<Tab>()` 重拉,**不做乐观更新**。例:删账号后 `renderAccounts()` |
| 失败处理 | API 抛 → `alert('xxx失败: ' + e.message)`,**不做自动重试**,**不做 toast 队列** |

### SSE 处理范式

```js
function renderRuns() {
  paintRuns(state.runs);                                    // 1. 首先用已有 state 渲染(可能为空)
  if (state.runsEventSource) state.runsEventSource.close(); // 2. 关掉旧流(切回此 tab 重新订)
  state.runsEventSource = new EventSource('/api/runs/stream');
  state.runsEventSource.addEventListener('runs', (e) => {
    try { state.runs = JSON.parse(e.data); paintRuns(state.runs); } catch {}
  });
  API('/runs').then(rs => { state.runs = rs; paintRuns(rs); }).catch(() => {}); // 3. 首屏兜底
}
```

切 tab 时关流:

```js
// navigate() 内
if (tab !== 'runs' && state.runsEventSource) {
  state.runsEventSource.close();
  state.runsEventSource = null;
}
```

---

## Common Mistakes

| 反模式 | 为什么不要 | 怎么改 |
|--------|------------|--------|
| 引入 Redux / Zustand | 项目规模无需,反而增加心智 | 用 `state` 对象 + 直接赋值 |
| 给 `state` 加 setter / proxy / Object.defineProperty | 没有 UI 自动 reactive 系统,加 setter 也没人订阅 | 直接 `state.x = newVal; render<Tab>();` 显式触发重绘 |
| 在 `state` 里存 DOM 元素 | DOM 在 `navigate()` 重新 cloneNode 时换新,旧引用失效 | 每次 render 函数内 `$('#...')` 重新取 |
| 在 `state` 里存派生数据(`state.accMap`、`state.runningCount`) | 源 state 变更时容易忘同步,变陈旧 | render 时算 `const accMap = ...`,丢弃即可 |
| 切 tab 时不关 `EventSource` | 后台流量持续,且事件 listener 越积越多 | `navigate()` 里有专门清流逻辑,follow it |
| 多个 modal 共用 `state.modal` 字段 | 关一个会清另一个的数据 | 每个 modal 用自己的命名空间:`state.accLogin / state.runDetail` |
| 用 `state` 缓存 form 输入 | form 已经存在 DOM 里,二次拷贝双向同步是 bug 之源 | 提交时 `new FormData(form)` 一次取出 |
| 在 SSE 处理回调里再去 `await API(...)` 二次拉 | 1Hz 推送 × 二次拉 = 流量灾难 | SSE 帧自己已包含全量,直接用 |
| 把 URL hash 状态镜像进 `state.currentTab` | 双向同步出 bug 时 UI 和路由对不上 | 用 `currentTab()` 函数每次读 `location.hash`,单一来源 |
