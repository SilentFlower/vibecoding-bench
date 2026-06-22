# 兼容 capture run 继续对话抓包

## Goal

让 `vibecoding-bench` 的 capture run 在点击“继续”后仍然能完整抓包，把用户后续输入的 `/cost`、`/context`、主模型请求、`count_tokens` 等 HTTP 流量追加保存到原 run 的 flows 目录，便于复现和分析 Claude Code 后续操作。

## Background / Known Context

- 当前普通 capture run 会启用完整 HTTP 抓包，并把 `http_capture.jsonl`、`capture_index.json`、`stats.jsonl` 和 `.flow` 写入 `data/flows/<account>/<task>/<run>/`。
- 当前 continue 流程会启动 `bench-continue-sidecar-*`，worker 也会共享 sidecar 网络命名空间，请求会经过 sidecar。
- 当前 continue sidecar 只挂载 `/ca`，没有挂载原 run 的 `/flows` 目录。
- 当前 continue sidecar 没有设置 `CAPTURE_FULL_HTTP=1`、`CAPTURE_SCOPE=all` 等完整抓包环境变量。
- 远程 run `1b19b983b62f` 后续 `/cost`、`/context` 没有追加到原 capture files，说明不是解析遗漏，而是 continue 完整抓包没有持久化到原 run 目录。

## Requirements

- capture run 启动 continue 会话时，必须继承完整 HTTP 抓包能力。
- continue 后产生的完整 HTTP 记录必须写回原 run 的 `flows_dir`，并追加到原有 `http_capture.jsonl` 和 `capture_index.json`。
- continue 后产生的 mitm stream file 必须落在原 run 的 flows 目录，文件名可继续使用 sidecar 当前时间戳命名。
- 普通非 capture run 的 continue 行为不得被强制升级为完整抓包，避免扩大敏感数据落盘面。
- continue 逻辑必须复用现有 sidecar recorder 机制，不引入新的抓包格式。
- WebUI run 详情页应能通过现有 capture 文件读取路径看到 continue 后新增的索引记录，不要求新增独立页面。
- 失败时必须保持当前清理语义：continue sidecar 或 worker 启动失败后清理已创建容器。

## Acceptance Criteria

- [ ] 对一个 capture run 点击继续并输入 `/context` 后，原 run 的 `http_capture.jsonl` 行数增加。
- [ ] 对一个 capture run 点击继续并输入 `/cost` 后，原 run 的 `capture_index.json` 中能看到新增 HTTP flow 索引。
- [ ] 原 run 的 flows 目录中出现 continue sidecar 新生成的 `.flow` 文件，或在 `SAVE_FULL_FLOWS=0` 以外的 capture 继承路径下明确保持 `SAVE_FULL_FLOWS=1`。
- [ ] 对普通非 capture run 点击继续时，不创建完整 `http_capture.jsonl` 正文抓包文件。
- [ ] continue 会话启动失败时不会留下 `bench-continue-*` 残留容器。

## Definition of Done

- 代码改动集中在 continue 容器启动和 capture 判定路径。
- 已补充或更新最小必要测试；如果项目没有对应自动化测试能力，需要记录手工验证命令和结果。
- 已运行相关静态检查或语法检查。
- 不提交抓包正文、token、Cookie、prompt 等敏感数据。

## Out of Scope

- 不改变普通 run 的抓包策略。
- 不新增单独的 continue capture 页面。
- 不改 sidecar recorder 的完整抓包 JSON schema。
- 不处理 `cc2api` 的 `/v1/messages/count_tokens` 兼容；该事项保留在独立任务 `06-15-cc2api-count-tokens-compat`。
