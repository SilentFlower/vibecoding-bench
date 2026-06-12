# cc2api 2.1.173 抓包差异分析设计

## Technical Design

本任务只在 `vibecoding-bench` 仓库保存任务文档和安全摘要，真实抓包原文留在 `data/flows/**` 本地数据目录，不纳入 git。

拉取阶段使用远程部署配置中的 SSH 信息，只同步用户指定的三条 run 目录。同步目标保持 `data/flows/<account>/<topic_id>/<run_id>/` 层级，便于复用现有抓包分析脚本和历史任务引用。

分析阶段从 `capture_index.json` 和 `http_capture.jsonl` 读取数据，但报告只输出：

- run 路径、文件大小、flow 数量、endpoint 计数；
- header 名称顺序、少量非敏感 header 值、状态码；
- billing 行中的 `cc_version`、`cc_entrypoint`、`cch` 短值；
- body 顶层 key、模型名、beta 列表、CCH 复算命中数；
- telemetry 的事件名、字段路径、版本字段和模型字段。

不输出 Authorization、Cookie、OAuth token、账号邮箱、完整 prompt、完整响应体、完整 `.flow` 内容。

CCH 复算采用既有 `2.1.172` 结论作为第一假设：

- seed：`0x4D659218E32A3268`；
- 输入先把真实 `cch=<5hex>` 替回 `cch=00000`；
- 对 `2.1.172+` 主请求尝试排除 top-level `model` 值、top-level `max_tokens` 字段、top-level `fallbacks` 字段；
- 保留旧版本完整 body 规则作为对照。

`cc_version` 后缀复算采用既有 JS UTF-16 code unit 索引语义，并优先取首条 user message 的最后一个 text block。每个样本输出命中数，不把用于计算的完整 prompt 写入报告。

对 Fable `[1m]` 与未指定 `[1m]`，分析矩阵按最终请求模型和 `anthropic-beta` 是否包含 `context-1m-2025-08-07` 分组，不只按 UI 上的 model override 字符串推断。

代码升级阶段在独立仓库 `/root/project/cc2api` 内完成，保持单一版本画像来源：

- `src/service/version_profile.rs` 只改默认版本、基础版本、build time 和注释。
- `src/service/access_policy.rs` 只扩默认允许范围到 `2.1.173`。
- `src/service/rewriter.rs` 只把 `2.1.173` 纳入既有 `2.1.172` CCH seed / top-level 输入规范化规则，并更新测试期望。
- `src/service/telemetry.rs` 测试继续引用默认版本常量，避免未来补丁版本升级时散落硬编码。
- `web/src/components/Settings.vue` 与 README 同步默认允许范围和说明。

本次不改 `allow_1m_models` 的数据结构、默认值或匹配规则。它仍然只决定客户端已有 `context-1m-2025-08-07` 是否能透传；`2.1.173` Fable `[1m]` 抓包显示主请求不带 `context-1m`，因此不新增自动注入逻辑。

## Rollout / Rollback

若拉取过程中同步到错误目录，删除对应新 run 本地目录后重新同步即可。若分析报告误写敏感内容，必须先从任务文档中删除，再继续后续工作。

代码升级回滚只需撤销 `/root/project/cc2api` 中版本画像、准入范围、CCH 分支和文档测试期望的对应修改；因为不做 schema 变更，也不改变账号 1M 白名单语义，回滚面较小。
