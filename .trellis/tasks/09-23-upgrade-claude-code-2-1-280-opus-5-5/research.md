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

## 抓包环境缺口

只读检查发现本地数据库无账号，仅存 profile 凭据已过期。对文档记录的远程主机做 BatchMode SSH 读取时，主机密钥与 known_hosts 不一致而被拒绝。未绕过 SSH 校验、未修改 known_hosts。等待当前抓包实例地址或目标版本 run ID，cc2api 保持 2.1.260。
