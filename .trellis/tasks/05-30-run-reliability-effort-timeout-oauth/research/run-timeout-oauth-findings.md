# 远程 run 超时与 OAuth 竞态发现

## 样本

- `038e18dac0cf`：文章转播客，`timeout`，`exit_code=124`，运行约 3035 秒。
- `c9385c530dbe`：个人记账，`timeout`，`exit_code=124`，运行约 3037 秒。
- `17e64e4f6b22`：AI 写作风格迁移，`timeout`，`exit_code=124`，运行约 3038 秒。
- `a4ded70d095f`：时间块周历，`timeout`，`exit_code=124`，运行约 3037 秒。
- `46a9e72ed5eb`：本地知识库 Chat，`timeout`，`exit_code=124`，运行约 3037 秒。

## 观察

- 样本中的 Anthropic `/v1/messages` 已完成响应基本为 HTTP 200，没有看到 429/5xx 主导问题。
- 多个 run 发生在“仍在写代码/验证/调研/等待后台任务”状态，未生成最终 assistant 文本，因此 worker 到 deadline 后退出 124。
- 当前 worker 的成功判定依赖 Claude session JSONL 最后一条稳定的 assistant 文本；如果停在 tool_use/tool_result 或没有最终总结，会继续等到 timeout。
- OAuth 后台刷新器会原子更新 profile credentials，但已启动 worker 使用的是启动时拷贝的私有 credentials，运行中不会自动同步刷新后的 token。

## 设计影响

- 不应把这些 timeout 归因于远端 API 故障。
- 应减少默认过度思考和无界调研。
- 应在临近 timeout 时主动让 Claude 收尾。
- 应让运行中 worker 单向同步 profile credentials，并在 401 时快速恢复或明确 auth 失败。
