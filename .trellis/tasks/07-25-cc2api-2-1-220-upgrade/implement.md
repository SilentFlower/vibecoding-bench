# 升级 cc2api 至 Claude Code 2.1.220 - 实施计划

## Steps

1. 扩展版本画像。
   - 新增 `PROFILE_2_1_220` 并切换默认 identity/access policy。
   - 为 request、telemetry、bootstrap 增加实现所需的显式版本字段，补 profile 完整性和回滚唯一性测试。

2. 版本化请求 header/body。
   - Rewriter 按账号 profile 选择 Opus/Fable/Haiku beta。
   - 2.1.220 Opus 5 增加 fallback-credit；Fable fallback 改为 Opus 5。
   - Opus 5/Fable 默认 64000，增加 2.1.220 Fable 专用 body order。
   - TokenTester 使用 canonical env 对应的 identity/request profile。

3. 接入 billing 版本分支。
   - 将 2.1.220 加入 CCH 2172+ 输入规范化和 seed 映射。
   - 增加 Opus/Fable、cc_version 多 text block、diagnostics 与嵌套同名字段回归测试。

4. 更新全局 settings 与迁移。
   - 更新 system-role 和 assistant-prefill 默认模型列表。
   - 增加旧默认精确值迁移、幂等测试和自定义值保留测试。
   - 迁移 2.1.197 默认 profile/allowed range，并同步账号 canonical env。

5. 对齐 bootstrap。
   - Configured 模式按 profile/query 注入 `cedar_basin`、`marigold`、`belladonna`。
   - 保持 passthrough、hide_fable 和 gzip 行为，补 Opus 5/Fable 5 测试。

6. 增加公开连通性端点。
   - 在鉴权 fallback 前注册 `GET/HEAD /api/hello`。
   - 测试无 token 返回 200、GET JSON 正确、其他 fallback 仍要求 token。
   - 用 2.1.220 本地探针确认 hello 是否使用 `ANTHROPIC_BASE_URL`；当前证据为固定访问官方域名，因此不修改 new-api。

7. 修正自动 telemetry 画像来源。
   - 基础 beta 和启动默认模型改从选中 profile 读取。
   - 保留最终请求 beta 覆盖和原生事件未知字段透传。
   - 补 2.1.220 Opus/Fable、旧 profile 回滚及不伪造 CLI flag 测试。

8. 同步管理前端和 bench 默认版本。
   - Settings fallback profile/default/placeholder 更新到 2.1.220。
   - worker Dockerfile/entrypoint、compose、orchestrator 默认值与测试、WebUI datalist、README 同步到 2.1.220。

9. Focused validation。
   - `cd cc2api && cargo fmt --check`。
   - `cd cc2api && cargo test cch`。
   - 运行 version profile、rewriter、gateway hello/bootstrap、telemetry、migration 定向测试。
   - `cd cc2api/web && npm run build`。
   - 运行根仓受影响 Python 测试和两份 compose config 检查。
   - 核对 `/root/project/new-api` 业务代码保持零 diff，并保存脱敏探针结论。

10. Full validation。
    - `cd cc2api && cargo test`。
    - 检查 git diff 不包含抓包正文、token、Cookie、邮箱或账号标识。

## Risky Files

- `cc2api/src/service/version_profile.rs`
- `cc2api/src/service/rewriter.rs`
- `cc2api/src/service/oauth.rs`
- `cc2api/src/service/telemetry.rs`
- `cc2api/src/service/gateway.rs`
- `cc2api/src/store/settings_store.rs`
- `cc2api/src/store/db.rs`
- `cc2api/src/handler/router.rs`
- `cc2api/web/src/components/Settings.vue`
- `images/worker/entrypoint.sh`
- `orchestrator/main.py`

## Rollback Points

- 保留 `2.1.197` 内置 profile，可在管理端显式切回。
- settings 迁移只处理精确旧默认值，自定义配置无需恢复。
- `/api/hello` 为独立公开路由，可单独回退且不影响其他鉴权路径。
- new-api 当前没有 hello 业务改动；后续客户端行为变化时需重新抓包评估。
- 根仓默认版本只影响未配置覆盖值的新 worker，可通过 `.env` 或 WebUI 覆盖回 2.1.197。

## Pre-Start Checks

- 确认任务 brief 与 PRD/设计/实施计划一致。
- 确认实现和检查 manifest 均包含协议、后端、前端/部署和本任务抓包研究条目。
- 开始实现前加载 `trellis-before-dev`，并通过 `trellis-route(target=implement)` 决定执行方式。
