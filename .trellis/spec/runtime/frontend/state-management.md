> 本文源码路径及命令以 `services/runtime/` 为工作目录。

# 日志页面状态合同

## Scenario: 筛选、详情及阶段原文

### 1. Scope / Trigger

- web/client.ts 管理原生页面状态；类型与 API 解码来自 src/shared/contracts.ts、src/shared/log-api.ts。
- 本页属于只读控制台，不承担账号操作或模型提交。

### 2. Signatures

- decodeLogList(value: unknown): { rows: RequestRow[]; total: number }。
- decodeLogDetail(value: unknown): RequestDetail。
- loadList(): Promise<void>；openDetail(id: string, refresh = false): Promise<void>。
- GET /api/logs 使用 requestId、model、state、requestClass、sessionId、since、until、limit、offset。
- GET /api/logs/:id 读取快照；GET /api/health 返回 engine、logMode、captureError、nativeFinalCapture，以及 tlsCapture、tlsVerifier、upstream 的安全状态摘要。

### 3. Contracts

- 分页 limit=50，offset 从 0 开始，下一页依据 total。筛选修改、重置和同会话查看都从第一页开始。
- UI 本地时间筛选转换为 ISO UTC；requestId 为包含匹配，模型、类别、状态和 session 为精确匹配。
- 列表和详情各有独立 AbortController；旧请求不能覆盖新筛选或新详情，关闭对话框后不得写回旧结果。
- 开启自动刷新后每 3 秒刷新列表；详情显式刷新，打开新 ID 重置到 summary/ingress，同 ID 刷新保留页签。
- 详情四页签为概览、头部处理、性能、原始数据；阶段名称与采集状态由持久接口驱动。
- 概览用 context.inputFormat 显示“原生 CC 正文接入”或“普通 API 原生组装”；有历史上下文但缺字段时显示“旧记录未注明”，context=null 的入口失败显示“未解析”。原生 cc_prepared 标签为“原生改写（中间值）”，普通 API 与旧记录仍为“CC 组装（中间值）”；两者都不能代替最终出站。
- 概览按 context.modelSelection 显示“入站模型”“前置选择模型”“模型选择来源”，来源为“本机启动配置”或“调用方请求”；历史缺证显示“旧记录未注明”，context=null 显示“未解析”。不得用当前配置替换历史发生时证据。
- null 性能字段显示未观测，不写 0；请求 state 与捕获 status 不相互替代。
- demo/fixture 必须明显标记演示与未调用上游。wire_final 不可用时显示未采集，不能以中间原文填充。
- tlsCapture=verify 时提示“最终 TLS 写出验证已开启（固定画像）”；tlsVerifier.state=failed 时显示“最终 TLS 验证器不可用”并提示需要重启实例。旧池能力提示为“独立 TLS 接收采样已开启”，关闭时为“最终出站值未采集”。nativeFinalCapture 是能力标记，不能显示成每次采样已成功。
- wire_final 的 native_tls_verifier 来源和 http_entity_from_final_tls_write 表示直接展示；完整/截断/失败状态由持久记录驱动，并显示最后本地写出不是上游实收证明。全页模型、状态及原文仍只按安全文本渲染。
- 文本、模型名、原文全部通过 textContent 渲染；不得通过 innerHTML 解释输入。复制只使用已经脱敏的接口文本。
- 同会话按钮用发生时的 sessionId 查询；父 agentId 与 agentId 保留快照，不依赖活跃进程对象。
- context.classification 按 purpose 显示“自动权限分类”“会话标题生成”或“会话压缩”，并显示固定 293 原生构造来源；类别与 querySource 的唯一映射和 profile 校验由 backend/runtime-contract.md 所有，页面复用共享解码器。其他原生请求显示“未识别特殊用途”，不把默认主类别当作已识别的特殊用途。
- 子代理详情消费服务端 agentAssociation 显示有效父代理/类型、逐字段来源和 explicit/linked/unknown/conflict/incomplete 状态；由证据补齐时另示发生时空值，证据按钮打开对应请求。页面不解析 Agent 文本，不把缺失类型当已知 custom；关联合同由 backend/logging-guidelines.md 所有。
- 表单子元素不能命名为 reset，以免覆盖 HTMLFormElement.reset()；当前按钮 ID 为 reset-filters。
- 复制提示在对话框打开时挂到 dialog 内，以免被原生顶层对话框遮住。

### 4. Validation & Error Matrix

| 条件 | 页面行为 |
| --- | --- |
| 无匹配记录 | 空态，禁用无效翻页 |
| 列表读取失败 | 加载失败说明与提示，不重放模型 |
| 详情不存在或过期 | 显示读取错误，不拼接当前进程内容 |
| text=null | 显示未保存原文，禁用正文复制 |
| wire_final unavailable | 明示未采集和采集位置原因 |
| captureError | 健康提示与采集异常信息，不能据此判定模型失败 |
| 浏览器拒绝剪贴板 | 提示手动复制，不把错误当作复制成功 |

### 5. Scenarios and Examples

- 正常：筛选 subagent，打开详情，查看父 agent，再点击同会话按钮看到主请求与子请求。
- 边界：summary 模式仍能显示关联与终态；没有正文时保持明确空值。
- 错误用法：看到 HTTP 200 就在页面判为成功。正确做法是显示服务端 RequestRow.state，区分 SSE 错误与缺失终态。
- 错误用法：使用 id=reset 的表单按钮后调用 form.reset()。正确做法是使用当前 reset-filters ID，关联筛选和重置均验收。
- 错误用法：把模型里的 HTML 或 JSON 原文通过 innerHTML 展示。正确做法是安全文本渲染，格式化 JSON 仍为文本。

### 6. Tests Required

- tests/browser/logs.spec.ts：列表与四页签、脱敏复制、最终值缺口、类别/时间筛选、同会话关联。
- 手机 390 像素宽度验收详情可读且页面不横向溢出。
- HTML/XSS 输入只显示为文本，不能创建节点或执行脚本。
- tests/browser/logs.spec.ts 另核对原生路径/中间值标签、demo 来源保留，以及入口失败不能被误标成旧记录；历史缺字段、分页与独立最终采样使用导入夹具核对。
- 改动异步读取或销毁流程时，核对 AbortController 与结果归属，关闭或换 ID 后旧响应不能覆盖页面。
- bun run typecheck 与 bun run build；浏览器验收使用独立目录、显式 demo 和无外网空间。
- tests/browser/logs.spec.ts 另覆盖迟到证据刷新、来源与原始上下文区分、证据跳转、分类用途、旧记录缺字段及 390 像素展示；tests/unit/log-api.test.ts 覆盖新字段空值/来源和分类协议一致性。
- tests/browser/logs.spec.ts 另覆盖前置模型、最后写出来源与验证器失效提示；手机 XSS 模型会在三处作为文本显示，不得创建节点。只读状态刷新不得提交 /api/requests。
