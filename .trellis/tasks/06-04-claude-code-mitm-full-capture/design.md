# Claude Code MITM 完整抓包分析模式设计

## Technical Design

### 范围边界

本任务在 vibecoding-bench 内新增“分析抓包 run”。它复用现有普通 run 的容器生命周期，差异仅体现在 run 元数据、sidecar 捕获配置、recorder 输出和 WebUI 入口。`/root/project/cc2api` 只作为后续消费者，不在本任务修改。

### 数据模型

在 `runs` 表增加可选列：

- `run_kind TEXT DEFAULT 'normal'`：`normal` 或 `capture`。
- `capture_mode TEXT`：初版使用 `full_http`。
- `capture_summary_path TEXT`：结构化索引文件相对或绝对路径。

兼容旧库通过 `_ensure_column` 补列。

### API 设计

新增 `POST /api/captures/run`：

请求体：

```json
{
  "account_id": 1,
  "topic_id": 12,
  "timeout_sec": 1800,
  "prompt": null
}
```

行为：

- 校验账号存在且启用。
- 校验 topic 存在且未删除。
- 创建一条专用 task，prompt 复用 `_default_prompt_for_topic()`，允许用户覆盖。
- 创建一条 `runs`，`run_kind='capture'`，`capture_mode='full_http'`。
- 调用 scheduler 提交 run。

新增或扩展 `GET /api/runs/{rid}/capture`：

- 返回抓包索引摘要、文件路径、文件大小。
- 对 header 值做脱敏，避免 UI 直接展示 bearer token、cookie、oauth token。

可选下载接口：

- `GET /api/runs/{rid}/capture/files/{name}` 下载允许的抓包文件。
- 初版可以先依赖现有 `/api/runs/{rid}/files` 展示文件树。

### Runner / Sidecar 配置

普通 run 保持现状。分析 run 调用同一个 `Runner.start_run()`，但 task dict 中传入：

- `capture_full_http=True`
- `capture_mode='full_http'`

Runner 根据该标记给 sidecar 注入：

- `SAVE_FULL_FLOWS=1`
- `CAPTURE_FULL_HTTP=1`
- `CAPTURE_TARGETS=anthropic.com,claude.com`
- `CAPTURE_MAX_BODY_BYTES=0`，表示请求体和响应体默认全文保存、不截断。

这样不会改变全局 `SAVE_FULL_FLOWS=0` 的普通 run 默认行为。

### recorder.py 输出

保留现有 `stats.jsonl` 摘要，新增只在 `CAPTURE_FULL_HTTP=1` 生效的完整 HTTP JSONL：

- `/flows/http_capture.jsonl`：每行一条目标 flow 的完整结构化记录。
- `/flows/capture_index.json`：run 结束过程中持续重写或最终由 recorder 追加维护的轻量索引。

记录结构建议：

```json
{
  "ts": 1780560000.0,
  "flow_id": "abc",
  "request": {
    "method": "POST",
    "scheme": "https",
    "host": "api.anthropic.com",
    "path": "/v1/messages",
    "query": "...",
    "headers": {"x-anthropic-billing-header": "..."},
    "body_text": "...",
    "body_base64": null,
    "body_encoding": "text",
    "body_bytes": 1234
  },
  "response": {
    "status": 200,
    "headers": {"content-type": "text/event-stream"},
    "body_text": "...",
    "body_base64": null,
    "body_encoding": "text",
    "body_bytes": 5678
  },
  "analysis": {
    "billing_header": "...",
    "cc_version": "2.x.x.xxx",
    "cc_entrypoint": "cli",
    "cch_headers": {},
    "usage": {}
  }
}
```

body 处理规则：

- UTF-8 / JSON / SSE / text 类型保存 `body_text`。
- 二进制或解码失败保存 `body_base64`。
- `content-encoding` 解压由 mitmproxy 的 `get_text()` 优先处理，失败退回 raw bytes。
- 分析抓包模式默认保存请求体全文和响应体全文；普通 run 不启用该逻辑。

### 敏感数据处理

本地完整文件是分析资产，可能含 token、prompt、代码和响应。UI/API 预览必须脱敏以下 header：

- `authorization`
- `cookie`
- `set-cookie`
- `x-api-key`
- `x-stainless-arch` 以外的未知密钥类字段按名称匹配 `token|secret|key|credential`

`http_capture.jsonl` 可以保存原始值，但文档必须提示只在可信本机使用，不提交仓库。

### WebUI

增加一个轻量入口，推荐放在 runs tab 顶部：

- account 下拉；
- topic 下拉或筛选；
- timeout；
- prompt override 可选；
- `启动抓包` 按钮。

run 列表对 `run_kind='capture'` 显示 `capture` 标记。run 详情增加“抓包”区块：

- capture 文件可用状态；
- `http_capture.jsonl`、`capture_index.json`、mitm `.flow` 的路径和大小；
- 关键指纹摘要：已观察到的 `cc_version`、`cc_entrypoint`、CCH/header 名称。

### Rollout / Rollback

Rollout：

- SQLite 加列向后兼容。
- 普通 run 默认配置不变。
- 新环境变量只在 capture run 注入。

Rollback：

- 前端入口可隐藏；
- 后端新增接口不影响旧接口；
- `run_kind` 为空或旧库默认视为 `normal`。

### 风险

- 完整请求/响应体可能占用较多磁盘。
- 抓包资产含高敏数据，不能提交仓库或暴露到不可信网络。
- Claude Code 后续若启用证书 pinning，MITM 捕获会失败；本任务只报告失败，不绕过 pinning。
