# 升级 Claude Code 2.1.280 并支持 Opus 5.5

## 目标

将 vibecoding-bench 运行时和 cc2api 默认协议画像升级到 2.1.280，支持选择、运行和代理 `claude-opus-5-5`，保留旧 run、旧画像与管理员自定义配置。

## 已确认事实

- 用户要求两个项目升级到 Claude Code 2.1.280 并支持 Opus 5.5。
- 2026-09-23 npm registry 已确认目标包存在；官方已发布精确模型 ID，见 `research.md`。
- bench 当前默认 2.1.260（`orchestrator/main.py:189`、`images/worker/Dockerfile:13`），默认模型为 `opus[1m]`。抓包输入可自由填写模型，但候选缺少 Opus 5.5（`webui/index.html:275`）。
- cc2api 默认 2.1.260（`cc2api/src/service/version_profile.rs:6`），已使用精确模型子画像和 SQLite/PostgreSQL 双栈迁移。
- 旧任务已实现 `runs.claude_code_version` 快照，本次复用该契约。
- 本地 data JSON/JSONL 未找到 2.1.280 或 Opus 5.5 样本；wire 差异需真实抓包。

## 需求

### R1：bench 运行时与模型入口

- 同步 worker 镜像、entrypoint、orchestrator、Compose、示例配置、WebUI、README 中的当前默认版本到 2.1.280；历史记录和兼容测试按含义保留。
- 核对普通、批量、养号、抓包、继续对话及 quota、OAuth refresh、login worker。
- 模型候选增加 `claude-opus-5-5`；其 `[1m]` 形式经目标 CLI 解析验证后再列入。
- 保留自由输入、已有别名和单 run 覆盖；不强行改写既有账号或全局模型选择。
- 页面版本覆盖继续高于环境默认值，旧 run 与排队 run 继续使用创建时版本快照。

### R2：真实协议证据

- bench 更新后取得实际 2.1.280 版本输出、模型解析结果与脱敏抓包摘要。
- 覆盖 Opus 5.5 单轮、工具、多轮、继续对话；核对现有 Opus 5、Sonnet 5、Fable 5.1、Haiku 及出现的 title/probe/aux。
- 比对 identity、SDK/runtime、UA、header/beta 顺序、body 字段与顺序、thinking、effort、max_tokens、fallbacks、CCH、cc_version、bootstrap/cwk 和后台端点。
- CCH 先用旧 seed 复算；不得因版本接近直接复制 2.1.260 常量。
- 未观察项明确标记。必要样本缺失时暂停 cc2api 默认画像切换，先交付可采集的 bench 改动，整体任务保持未完成。
- 原始 flow、凭据和真实正文留在忽略目录，仅提交脱敏矩阵与最小 fixture。

### R3：cc2api 与 Opus 5.5

- 基于 R2 新增独立 2.1.280 画像和精确 Opus 5.5 子画像，完整保留 2.1.260 及历史画像。
- 对齐访问范围、账号 canonical env、API 补齐、原生 CLI 转发、telemetry、bootstrap 与管理页。
- CLI 参数使用抓包确认值，不能用官方 API 默认 effort 推导 CLI 值。
- Opus 5.5 始终开启思考、强制工具调用不受支持、工具间进度可能走 thinking block；这些能力纳入回归，不套用旧 Opus 参数假设。
- 显式参数继续服从既有设置语义，不默认新增将 `tool_choice=any|tool` 改为 auto 等有损转换；保留上游校验错误。
- 核对 system role、1M、assistant prefill 与 bootstrap 列表，按证据补充精确新模型；既有可选兼容开关不借升级自动开启。

### R4：迁移与验证

- `claude_code_version_profile` 与 `allowed_claude_code_versions` 仅在仍为旧默认组合时自动迁移；自定义任一项时保留显式配置。
- 模型列表只迁移已知旧默认值，保护自定义列表与账号策略。
- 账号 identity 与实际选定画像一致；SQLite/PostgreSQL SQL 成对处理，迁移幂等。
- 运行 bench 单测、shell/JS 与 Compose 检查，以及 cc2api 格式、Rust 回归和前端构建；真实验证与单测分开报告。

## 验收标准

- [ ] R1：新 worker 实际执行 2.1.280，API/任务快照与运行版本一致。
- [ ] R1/R4：切换全局版本后，旧 run 和排队 run 仍使用自身快照，新 run 使用新配置。
- [ ] R1/R2：页面可选 Opus 5.5，上游实际模型为 `claude-opus-5-5`。
- [ ] R2：脱敏证据可复算，CCH、cc_version、beta/body 顺序与真实样本一致。
- [ ] R3：API 与原生 CLI 路径的 Opus 5.5 单轮、工具、多轮、继续对话可用；其他模型回归通过。
- [ ] R3/R4：新安装默认 2.1.280，旧默认正确升级，自定义/回滚组合和历史画像保持可用。
- [ ] R4：必要检查通过，未执行的真实验证明确列出，完成前不标记整体完成。

## 范围边界

- 本任务产出代码、配置、证据、测试与文档；Git 推送、镜像发布和生产部署在具体结果就绪后按对应流程处理。
- 不改真实账号凭据、不删除原始抓包、不重构整个画像系统或添加无关模型。
- Flower 同步是独立工作，不纳入本业务任务的验收或完成标记。
