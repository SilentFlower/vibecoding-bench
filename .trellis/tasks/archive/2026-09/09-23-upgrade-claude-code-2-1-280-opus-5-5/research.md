# 升级前证据

## 2026-09-23 官方发布核对

执行 `npm view @anthropic-ai/claude-code@2.1.280 version dist.tarball --json`，返回版本 2.1.280，包地址为 https://registry.npmjs.org/@anthropic-ai/claude-code/-/claude-code-2.1.280.tgz 。GitHub 对应 release 页本次返回 404，不影响 registry 已发布事实。

官方模型页：https://platform.claude.com/docs/en/models/opus-5-5/overview 。已确认 API ID `claude-opus-5-5`，发布日期 2026-09-22。模型始终启用 adaptive thinking，不支持强制工具调用；部分工具间进度通过 thinking block 返回。这些约束用于回归，不用于推导 CLI 的 beta/CCH/cwk 或默认 effort。

## 现状

bench 默认 CLI 2.1.260、模型 `opus[1m]`，已有 run 版本快照。cc2api 默认 2.1.260，使用聚合版本画像和精确模型子画像。Settings.vue 多处初始化/API fallback/恢复默认需要同步审计。

本地 data 的 JSON/JSONL 搜索未找到 2.1.280 或 claude-opus-5-5 样本。后续须确认目标 CLI build_time、SDK/runtime、别名解析、header/beta/body 顺序、thinking/effort、fallback、CCH、cc_version、bootstrap/cwk 与后台端点。

## 可复用材料

- `.trellis/tasks/archive/2026-09/09-04-vibecoding-bench-claude-code-2-1-260-runtime/implement.md`
- `.trellis/tasks/archive/2026-09/09-04-claude-code-2-1-260-capture-evidence/research.md`
- `.trellis/tasks/archive/2026-09/09-04-claude-code-2-1-260-capture-evidence/research/analyze_capture.py`
- `.trellis/tasks/archive/2026-09/09-04-cc2api-claude-code-2-1-260-protocol/implement.md`

历史材料用于分析方法和回归约束，不能作为新版本 wire 事实。

## 上下文读取提醒

协议升级规范约 58 KB，超过自动上下文注入的 32 KB 上限。实现与检查阶段必须分段读取完整适用章节，不能把注入截断当成规范末尾。

## 2026-09-23 bench 实施证据

- Docker 原 Dockerfile 构建 `vibebench-worker:check-2.1.280` 成功，安装输出 `2.1.280 (Claude Code)`。
- 无网络、无账号挂载的临时容器实际运行 entrypoint 登录模式，出现版本 ready/idling；node 用户执行 `claude --version` 为 2.1.280，检查后容器已删除。
- 在临时 Python venv 安装仓库 requirements，复用宿主 Node；完整 unittest 59 项通过。最初宿主缺 docker SDK，旧 orchestrator 镜像缺 node，均是测试环境问题，已由临时环境解决。
- `bash -n images/worker/entrypoint.sh`、`node --check webui/app.js`、两份 Compose `config --quiet`、HTML 候选和共享 datalist 绑定检查通过。
- 使用目标镜像、`--network none`、本地 HTTP 桩、占位 API key 和 `claude --bare --print --model ...` 检查模型解析；桩返回固定 400 结束请求，不调用真实上游。

| CLI 输入 | 请求 model | context-1m beta |
| --- | --- | --- |
| claude-opus-5-5 | claude-opus-5-5 | 无 |
| claude-opus-5-5[1m] | claude-opus-5-5 | 有 |
| opus[1m] | claude-opus-5-5 | 有 |

上述离线观测仅证明 CLI 模型解析，不能用作 cc2api 的 OAuth header/body/CCH/bootstrap 画像来源。

## 2026-09-23 真实 2.1.280 抓包

bench 镜像经 GitHub Actions 构建并部署到现有环境后，使用独立账号取得 Opus 5.5、
Sonnet 5、Fable 5.1、Haiku、Opus 4.8 和 Sonnet 4.5 样本。补充模型使用普通任务提示，
未在提示词中暴露抓包、协议或字段验证意图。原始 flow/JSONL 仅保存在被忽略的
`data/captures/2.1.280/`，任务文档不记录账号、凭据、真实正文或完整响应。

| 模型 | max_tokens | thinking | effort | 初始 fallback | bootstrap cwk |
| --- | ---: | --- | --- | --- | --- |
| `claude-opus-5-5` | 128000 | adaptive + updates | max | 无；后续辅助请求可为 `default` | saffron |
| `claude-sonnet-5` | 64000 | adaptive + updates | max | 无 | pewter |
| `claude-fable-5-1` | 64000 | adaptive + updates | max | 无 | sorrel |
| `claude-haiku-4-5-20251001` | 32000 | enabled 31999 + updates | 无 | 无 | null |
| `claude-opus-4-8` | 64000 | adaptive + updates | max | 无 | null |
| `claude-sonnet-4-5` | 32000 | enabled 31999 + updates | 无 | 无 | null |

共同 identity：build time `2026-09-21T20:40:17Z`，CLI UA
`claude-cli/2.1.280 (external, cli)`，telemetry UA `claude-code/2.1.280`，Stainless
`0.112.1` / Node `v26.3.0`，GrowthBook/session UA `Bun/1.4.3`，timeout `600`。
bootstrap 继续使用 `client_data.cedar_basin=2027-08-31` 和
`claude-fable-5-1[1m]` 额外入口。Opus 5 未在本轮 2.1.280 样本中出现，代码只保留
2.1.260 的历史兼容子画像，不将其写成 2.1.280 新证据。

beta 的关键新增项为 `mid-conversation-tool-changes-2026-07-01`、
`mid-conversation-system-clear-at-2026-08-21`、`thinking-binding-controls-2026-08-01`，
Sonnet 5 / Opus 4.8 还带末尾 `message-threads-2026-08-12`。Opus 5.5 `[1m]` 仍把
`context-1m-2025-08-07` 放在 oauth 后。出现 `fallbacks="default"` 的 Opus 5.5
辅助请求同时加入 server-side-fallback/fallback-credit token；初始主请求不带这三项。

## CCH 根因

先以旧 seed `0x4D659218E32A3268` 复算未命中。随后对 2.1.280 可执行文件的原生 CCH
路径做调试，确认 seed 没变，归一化规则变为：

1. 把 billing header 中的 CCH 恢复为 `00000`。
2. 清空序列化 JSON 中每个 key 字节精确等于 `"model"` 且 value 为字符串的字段，
   不只顶层 model；advisor 工具定义中的嵌套 model 也会计入。
3. 删除顶层 `max_tokens`，保留 fallback 与其他字节、顺序和转义。

Opus/Fable 请求含 advisor 工具的嵌套 model，正是旧 cc2api 只清空顶层 model 后 CCH
不一致的直接原因。用这条规则对已下载的 Opus 5.5、Sonnet 5、Fable 5.1、Haiku、
Opus 4.8、Sonnet 4.5 所有 billing 请求复算，全部与原生 CCH 一致。调试使用的临时
凭据副本和脚本已安全删除；提交内容只有脱敏结论与 synthetic fixture。
