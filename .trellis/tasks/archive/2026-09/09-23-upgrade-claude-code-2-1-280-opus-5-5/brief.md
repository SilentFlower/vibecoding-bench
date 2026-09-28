# Brief — Claude Code 2.1.280 与 Opus 5.5 升级

- **目标（Goal）**：bench 运行时与 cc2api 默认画像升级到 2.1.280，支持 `claude-opus-5-5`。
- **范围（Scope）**：运行时默认值、模型候选、真实抓包、协议适配、设置/账号迁移、管理页与回归验证。
- **范围外（Non-Goals）**：生产部署和推送另按就绪结果处理；不改真实凭据、不清理抓包、不添加无关模型。
- **关键决定（Key Decisions）**：先升级 bench，取得真实证据后再切换 cc2api；保留旧 run 快照、旧画像、自定义设置和现有模型选择语义。
- **关键背景（Key Context）**：当前两项目为 2.1.260；涉及 worker/orchestrator、`version_profile.rs`、`rewriter.rs`、`db.rs` 和 `Settings.vue`。
- **风险与后续（Risks / Deferred）**：本地缺少 2.1.280 抓包；缺必要证据时先交付 bench，cc2api 保持未完成。Opus 5.5 的始终思考、强制工具限制与进度输出变化需单独验证。
- **验收（Acceptance）**：新 worker 版本和模型正确；Opus 5.5 单轮/工具/多轮/继续对话可用；协议可复算；旧版本、自定义设置和必要测试通过。
- **下一步（Next Step）**：启动任务，先实施 bench 默认版本与模型入口升级。
