# 升级 cc2api 到 2.1.197 - 实施计划

## 实施步骤

1. 更新版本画像注册表。
   - 在 `cc2api/src/service/version_profile.rs` 新增 `PROFILE_2_1_197`。
   - 默认 profile 切到 `2.1.197`，保留旧 profile。
   - 更新 profile 完整性和默认常量测试。

2. 更新 CCH / billing 版本分支。
   - `cc_version` 先按抓包已命中的现有后缀算法接入，并补 `2.1.197` 多 text block 回归测试。
   - CCH 将 `2.1.197` 接入 `CchProfile::ClaudeCode2172Plus` 和 seed `0x4D659218E32A3268`。
   - 增加 CCH 回归测试：`2.1.197` 命中 model 置空 + 删除 top-level `max_tokens` / `fallbacks`；`diagnostics` 保留；嵌套 tool schema 中的 `model` / `max_tokens` / `fallbacks` 不被误删。

3. 更新 `allow_1m_models` 默认与迁移。
   - 默认值从 `"opus"` 改为 `"opus,claude-sonnet-5"`。
   - 新账号创建、serde 默认、SQLite/PG `ALTER TABLE` 默认值同步。
   - 增加旧默认账号迁移：只把现有 `"opus"` 改成 `"opus,claude-sonnet-5"`，保留自定义值。
   - 测试 `claude-sonnet-5` 透传 `context-1m-2025-08-07`，`claude-sonnet-4-6` 继续过滤。

4. 更新 settings/profile 迁移。
   - 把 `2.1.195` 加入旧默认 profile 与 allowed range 迁移集合。
   - 测试旧默认组合升级到 `2.1.197`。
   - 测试管理员自定义 allowed range 不被自动覆盖。

5. 更新前端管理页。
   - `cc2api/web/src/components/Settings.vue` 默认 profile/fallback 列表加入 `2.1.197`。
   - `cc2api/web/src/components/Accounts.vue` 默认 `allow_1m_models`、快捷按钮和说明改为精确 Sonnet 5。
   - `cc2api/web/src/api.ts` 如无类型变化不改。

6. 更新 vibecoding-bench 默认版本配置。
   - `images/worker/Dockerfile`、`images/worker/entrypoint.sh`、`docker-compose.yml`、`docker-compose.remote.yml`、`README.md`、`webui/index.html` 中默认 `2.1.195` 改为 `2.1.197`。

7. 验证。
   - `cd cc2api && cargo fmt --check`。
   - `cd cc2api && cargo test`。
   - `cd cc2api/web && npm run build`。
   - 需要时补定向命令：`cargo test cch`、`cargo test version_profile`、`cargo test allow_1m`。

8. 远程验收准备。
   - 按 `.trellis/spec/vibecoding-bench/deploy/remote-deploy.md` 的 `cc2api.env` 协议整理远程命令。
   - 部署前检查连接数；连接高则暂停回报。
   - 部署后检查 `curl /`、DB 版本分布、settings allowed range、日志错误。

## 高风险文件

- `cc2api/src/service/version_profile.rs`
- `cc2api/src/service/rewriter.rs`
- `cc2api/src/service/gateway.rs`
- `cc2api/src/store/db.rs`
- `cc2api/src/model/account.rs`
- `cc2api/src/handler/router.rs`
- `cc2api/web/src/components/Settings.vue`
- `cc2api/web/src/components/Accounts.vue`
- `images/worker/entrypoint.sh`
- `docker-compose.yml`
- `docker-compose.remote.yml`

## 回滚点

- 后端 profile 保留 `2.1.195`，可通过设置页切回旧画像。
- 远程部署失败时回滚镜像 tag 或回退到上一父仓 gitlink。
- `allow_1m_models` 如需收紧，可在账号页或 DB 中改回 `"opus"`。
