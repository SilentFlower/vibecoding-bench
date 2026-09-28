# 技术设计

## 顺序与证据边界

按 bench → 真实抓包 → cc2api → 联合回归依次推进。bench 有独立验证结果，可先用于采集。缺少必要样本时 cc2api 保留当前已验证默认画像，整体任务保持未完成。

抓包沿用 sidecar/capture API，优先使用可用测试环境；若需要部署 bench 才能采集，先完成代码和验证，再按具体部署计划处理。历史分析器只提供分析方法，不为 280 提供未经验证的常量。

## bench

现有数据流为：环境默认版本 → 页面覆盖 → run 创建时快照 → scheduler payload → worker 环境 → entrypoint 安装/检查。继续对话使用历史快照，沿用 `runs.claude_code_version`，无需新增列。

模型继续使用自由字符串与 run 覆盖，增加 Opus 5.5 精确候选。保留默认别名 `opus[1m]` 的配置语义，通过抓包验证目标 CLI 对别名的解析。

涉及 orchestrator 主文件/测试、worker Dockerfile/entrypoint、两份 Compose、`.env.example`、`webui/index.html` 和 README；实施前再次搜索遗漏入口。

## cc2api

沿用 `ClaudeCodeProfile` 聚合 identity/access_policy/request/billing/telemetry/endpoints，通过 `MainRequestProfile.model_id` 精确登记 Opus 5.5。新 profile 的构建时间、SDK/runtime、beta、thinking/display、effort、max_tokens、fallback、CCH 与 cwk 均由抓包确认。

`rewriter.rs` 与 `gateway.rs` 保持 API 补齐和原生 CLI 路径的边界。新模型仅按契约补缺失字段，显式参数继续采用现有可选兼容开关和上游校验语义。仅在真实差异要求时扩展画像结构，并验证旧画像隔离。

## 持久化与前端

`settings_store.rs` 管理默认值，`db.rs` 幂等迁移旧默认组合。账号 `canonical_env.version/version_base/build_time/node_version` 与选定画像一致。自定义版本范围、画像或模型列表保持显式配置，两种数据库同步审查/验证。

`Settings.vue` 同步初始默认、API fallback、恢复默认、版本选项和文案。复用现有设置 API 与 reload 流程，需要接口变化时先检查 `web/src/api.ts` 定义。

## 验证与恢复

默认值断言与历史 wire fixture 分开处理，禁止全局替换所有 260。CCH 基于真实 body 字节复算，避免反序列化再序列化改变结果。

保留历史画像；生产部署/回滚沿用现有 SOP。后续部署时再核定实例、镜像和数据库快照。PostgreSQL 或真实流量环境不可用时明确报告未运行部分，不用静态审查冒充运行验证。
