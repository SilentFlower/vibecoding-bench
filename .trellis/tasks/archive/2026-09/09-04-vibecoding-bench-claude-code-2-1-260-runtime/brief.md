# Brief — 升级并发布 vibecoding-bench Claude Code 2.1.260

## Goal

- 将 bench 全部新 worker 默认升级到 2.1.260，修复 run 继续对话版本漂移并完成生产
  发布。

## Scope

- 更新 worker、orchestrator、Compose、env、WebUI、README 和测试中的默认版本。
- 为 `runs` 增加 `claude_code_version` 快照，覆盖普通、批量、养号、抓包和 continue。
- 构建、推送三镜像并部署生产，验证抓包与继续对话实际版本。

## Non-Goals

- 不修改 cc2api 画像和允许范围，不分析 2.1.260 wire 差异。
- 不改变模型、effort、代理、抓包隔离或 OAuth 所有权。

## Key Decisions

- 版本在 run 创建时固化，排队和全局设置变化不能改变该 run。
- continue 优先使用原 run 快照；历史空值回退当前有效版本并补写。
- 同一 task 再次运行创建新 run，使用再次运行时的新版本。
- bench 直接全量部署 2.1.260，不维护隔离环境。

## Key Context

- 实施前 `Runner.start_run()` 与 `Runner.start_continue()` 都独立读取全局有效版本。
- 修复后全部 run 创建入口保存 `runs.claude_code_version`，执行和继续会话复用该快照。
- 新增 nullable SQLite 列兼容旧库，新 run 必须非空，API 返回实际快照供核验。

## Risks / Deferred

- 所有 run INSERT 入口必须同时补齐，否则少见批量或养号路径仍可能漂移。
- 生产 WebUI 覆盖优先于 `.env`，部署时必须同时确认两者为 2.1.260。

## Acceptance

- 抓包以 2.1.260 创建后把全局改回 2.1.257，关闭并继续仍使用 2.1.260；新 run
  使用 2.1.257。
- 新旧 SQLite、全部 run 入口、所有 worker 路径、Compose 和单元测试通过。
- 三镜像同 SHA 发布，生产健康且普通/抓包/continue 的实际版本验证通过。

## Next Step

- 进入规格固化与提交发布流程，随后执行生产部署和实际 run/continue 验收。
