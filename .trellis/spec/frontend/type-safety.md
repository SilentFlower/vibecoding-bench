# Type Safety

> 本项目无 TypeScript,本文件描述本项目对应类型安全的等价物。

---

## Overview

**本项目前端是纯原生 JavaScript**(零构建 → 没有 TypeScript 编译步骤),**也不用任何运行时校验库**(无 Zod / Yup / io-ts / Joi)。

模板里这个文件保留,是为了说明:**在没有静态类型的前提下**,本项目用什么方式控制类型相关风险。等价物分三层:

1. **后端边界用 Pydantic 兜底**:所有进来的 API body 在 FastAPI 路由层用 `BaseModel` 校验,前端不需要再验
2. **前端写代码靠约定 + JSDoc 注释**(可选):字段名和类型在 render 函数顶部用注释标明
3. **DOM 层的 type-safety = `escapeHTML`**:任何字符串拼进 HTML 都过 `escapeHTML`,把"字符串当 HTML"的注入风险关掉

---

## Type Organization

无 TypeScript → 无 `interface` / `type alias`。当前**所有数据形状的真相**在两处:

| 数据 | 真相在哪 |
|------|----------|
| API 请求体形状 | `orchestrator/main.py` 的 `BaseModel`(`AccountIn / TaskIn / LoginStartIn`) |
| API 响应体形状 | `orchestrator/main.py` 路由 return 的字典 + DB 表 schema(`_SCHEMA` 字符串) |
| 前端全局 state 字段 | `app.js` 顶部 `const state = { ... }` 的初始化 |

**新增 feature 时**:
- 改后端 BaseModel **必须**同步改前端 `app.js` 里所有对应字段的引用(用 grep 找)
- 前端字段在 render 函数顶部用 JSDoc 注释标类型(可选但鼓励):

```js
async function renderTasks() {
  /**
   * state.tasks: Array<{
   *   id: number, topic_no: number, title: string,
   *   account_id: number, timeout_sec: number, repeat_n: number
   * }>
   */
  state.tasks = await API('/tasks');
  // ...
}
```

---

## Validation

**前端不做运行时校验**。约定:

| 验证类型 | 谁负责 | 怎么做 |
|----------|--------|--------|
| 用户输入(form) | 浏览器原生 + 后端 Pydantic | HTML5 属性(`required` / `pattern` / `type="number"` / `min` / `max`),提交后后端再校验 |
| 账号名格式 | HTML `pattern="[A-Za-z0-9_\-]+"` + 后端 `_ACC_NAME_RE` | 双层防御:前端立即提示,后端必再验 |
| 端口数 | HTML `type="number" min="1" max="65535"` | 浏览器拦截非数字 |
| 必填项 | HTML `required` | 浏览器拦截空提交 |
| 删除二次确认 | `confirm('删除账号 #' + id + '?')` | 浏览器原生 dialog |
| API 响应类型 | 不验 | 信任后端 contract;数据形状变化时同步改前端 |

**绝不引入** 前端校验库 —— 浏览器原生 + 后端 Pydantic 已经覆盖 P1 全部场景。

---

## Common Patterns

由于无类型系统,**类型相关的"模式"主要是写代码时的肌肉记忆**:

### 模式 1:从 API 响应取字段,带 fallback

后端返回的字段可能为 `null`(SQLite 列允许 NULL,Pydantic Optional),前端用 nullish 合并兜底:

```js
const dur = r.started_at && r.ended_at
  ? `${(r.ended_at - r.started_at).toFixed(0)}s`
  : (r.started_at ? `${(Date.now()/1000 - r.started_at).toFixed(0)}s` : '-');

const exit = r.exit_code ?? '-';                       // null/undefined → '-'
const tokens = stats.tokens_in ?? '-';
```

### 模式 2:数字字段必须显式 `Number(...)`

`FormData` 取出的是 string,送给后端的数字字段必须显式转:

```js
const body = {
  topic_no: Number(fd.get('topic_no')),
  account_id: Number(fd.get('account_id')),
  timeout_sec: Number(fd.get('timeout_sec')),
  repeat_n: Number(fd.get('repeat_n')),
  prompt: fd.get('prompt') || null,                    // 空串 → null,让后端走默认 prompt
};
```

### 模式 3:任何拼进 HTML 的字符串 → `escapeHTML`

**这条本质就是 type-safety**:把"任意字符串"显式标注为"安全的 HTML 文本",防 XSS。

```js
body.innerHTML = state.accounts.map(a => `
  <tr>
    <td><strong>${escapeHTML(a.name)}</strong></td>
    <td><code>${escapeHTML(a.profile_path)}</code></td>
  </tr>
`).join('');
```

**例外**:
- 数字字段不需要(`${a.id}` / `${a.upstream_socks5_port}`)
- 已知固定值的 enum 字段不需要(`${r.status}` 进 `pill-${r.status}` 这种,但**响应里的 status 必须是后端控制的枚举值**)

### 模式 4:enum 状态值 → CSS class 拼接

后端 `runs.status` 是有限枚举 `queued|running|success|failed|timeout`,前端直接拼成 class:

```js
`<span class="pill pill-${r.status}">${r.status}</span>`
```

风险:**后端新增 status 而前端不知** → 渲染出未定义的 `.pill-xxx`,样式回落到 `.pill` 基础样式(不会崩,只是视觉上没色)。**修复**:CSS 里 `.pill` 基础样式必须自带兜底色,见 style.css `.pill { color: var(--text-muted); }`。

---

## Forbidden Patterns

| 模式 | 为什么禁止 |
|------|-----------|
| `eval(jsonString)` 解析 JSON | 任意代码执行;用 `JSON.parse` |
| `new Function('return ' + str)()` | 同上 |
| 把 API 响应字符串拼进 `innerHTML` 不过 `escapeHTML` | XSS |
| 用 `setAttribute('onclick', userInput)` | XSS / 任意代码注入 |
| 直接 `element.innerHTML = userInputString` | XSS |
| `eval` / `with` / `arguments.callee` | 严格模式禁用 / 影响优化 / 已废 |
| 用 `document.write(...)` | 替换整个文档,且首屏后调用会清空页面 |
| 拼接 URL 不 `encodeURIComponent`(`/api/foo/${userName}`) | 含 `/` 等特殊字符的输入导致 404 / 路径混淆 | 用 `encodeURIComponent(userName)`,见 P2 改进项 |
| 在不知道返回类型的情况下做 `data.foo.bar.baz` | `Cannot read property of undefined` | 用可选链 `data?.foo?.bar?.baz` + nullish 合并 |
| 把 number 当 string 比较(`r.exit_code === '0'`) | 后端返回 number,比较恒为 false | 用 `r.exit_code === 0`,或 `Number(x) === 0` |
| 引入 TypeScript 但不上构建工具 | 浏览器跑不了 .ts | 要 TS 必须同时上 esbuild / vite;P1 不值,P2 评估 |
| 引入运行时校验库 | P1 用 HTML + Pydantic 已足够 | 真要校验时再加,先评估必要性 |

---

## Common Mistakes(略,见 component-guidelines.md 的 Common Mistakes —— escapeHTML 部分重复)

主要重复风险点:
1. **忘 `escapeHTML`**(详见 component-guidelines.md)
2. **忘 `Number(...)`** 转表单字段
3. **忘 `try/catch`** 包 `await API(...)`
4. **拼 URL 没 `encodeURIComponent`**(当前代码 ID 是 hex / int,暂时安全;含用户名 / 自由字符串的子路径未来必须处理)
