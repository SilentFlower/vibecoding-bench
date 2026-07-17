# 定时养号实施计划

## 1. 开发前确认

- [ ] 读取任务 `prd.md`、`design.md`、本文件及 curated JSONL 上下文。
- [ ] 读取 bench backend SQLite/error/quality 规范、frontend component/state/quality 规范。
- [ ] 读取 cc2api backend service/settings/testing 规范和 bench OAuth worker 同步规范。
- [ ] 确认父仓和 `cc2api` 子仓 git 状态，保留用户已有改动。

## 2. cc2api 凭据解析接口

- [ ] 在 `AccountService` 抽取带最小有效期和 force 参数的 OAuth 凭据解析逻辑，保留现有网关 5 分钟缓冲行为。
- [ ] 使用现有 cache lock 串行化 RT 刷新，并在刷新后重新读取最终账号。
- [ ] 新增管理员 DTO 和 `POST /admin/accounts/:id/oauth-credentials/resolve` 路由。
- [ ] 校验 OAuth/active 状态和 `min_validity_seconds` 范围，返回最小凭据响应，不记录 token。
- [ ] 补 Rust 单测：有效 AT 不刷新、临期刷新、force 刷新、非 OAuth/禁用拒绝、并发锁复用。

## 3. bench 配置与数据库

- [ ] 在 `.env.example`、本地/远程 compose 增加 cc2api 与 warmup 配置。
- [ ] 扩展 `_SCHEMA` accounts 列和唯一绑定索引。
- [ ] 在 `init_db()` 使用 `_ensure_column` 幂等迁移旧库并创建索引。
- [ ] 增加账号养号状态、间隔和绑定校验 helper，所有写入沿用 `_db_lock` 短事务。

## 4. cc2api 客户端与 profile 同步

- [ ] 实现 `Cc2ApiClient`：分页账号、创建账号、凭据解析和脱敏错误处理。
- [ ] 实现 bench profile 结构化读取、字段映射、代理 URL 组装和敏感字段边界。
- [ ] 实现 cc2api 凭据到 `.credentials.json` 的校验、合并和原子替换。
- [ ] 实现单账号安全创建/关联规则：UUID 优先、邮箱 fallback、冲突拒绝。
- [ ] 新增脱敏 cc2api 账号列表、单账号 sync、binding/warmup 更新、解绑 API。
- [ ] 绑定成功后让 OAuth 后台刷新器跳过本地 refresh，并从 cc2api 镜像最新凭据。
- [ ] 绑定账号额度查询走 cc2api；绑定期间阻止 bench 重授权。

## 5. managed OAuth worker

- [ ] Runner 为所有绑定账号的 task/capture/continue worker 注入 `CC2API_MANAGED_OAUTH=1`。
- [ ] worker managed 模式移除 run-local RT，禁用 local->profile credentials 回写。
- [ ] worker managed 模式的 profile->local 同步只接受更新 AT，并持续移除 RT。
- [ ] 401 时写凭据刷新请求标记、等待 profile 更新并最多重试一次，不调用本地 refresh endpoint。
- [ ] orchestrator 为 managed run 监听刷新请求，调用 cc2api force resolve 并原子更新 profile。
- [ ] 覆盖正常退出、失败、timeout、停止和 continue 路径，确保 `.claude.json`/`settings.json` 仍正常回写。

## 6. 养号调度与真实 run

- [ ] 实现 `WarmupScheduler` 生命周期、tick、原子认领和 stop。
- [ ] 实现临时同步失败 15 分钟重试、永久错误暂停和脱敏状态保存。
- [ ] 实现最近 20 个 warmup topic 排除和题库不足 fallback。
- [ ] 在事务中创建 `[warmup]` task 和 `run_kind=warmup` queued run，复用 `Scheduler.submit`。
- [ ] 实现立即运行 API，并与后台 tick 共用认领/启动逻辑。
- [ ] 在 run 终态更新最近状态、随机 next time、认证失败计数和三次自动暂停。
- [ ] 确认重启逾期只补一次、active warmup 不重复创建、手动任务仍共享账号信号量。

## 7. Accounts 与 Runs UI

- [ ] 扩展 Accounts 表格状态列和必要操作按钮，不新增批量同步。
- [ ] 新增养号配置 modal，加载脱敏 cc2api 账号列表并校验最小/最大小时。
- [ ] 实现同步、保存配置、立即运行、恢复和解绑交互及错误提示。
- [ ] Runs 列表增加 warmup badge，详情、停止、继续和删除行为保持兼容。
- [ ] 补充响应式样式并检查暗色/亮色主题、长错误文本和按钮不溢出。

## 8. 文档与规范

- [ ] 更新 README 的 Accounts/运行能力、cc2api 配置和单一凭据所有权说明。
- [ ] 更新远程部署文档和必要的 bench OAuth/DB 规范，记录 managed account 例外与调度契约。
- [ ] 文档和 fixture 只使用脱敏占位值。

## 9. 验证

- [ ] `python3 -m py_compile orchestrator/main.py`
- [ ] 运行新增 Python 单元测试，覆盖迁移、绑定、题库去重、调度认领、profile 合并和 cc2api 错误分类。
- [ ] `node --check webui/app.js`
- [ ] `bash -n images/worker/entrypoint.sh`
- [ ] 使用脱敏 credentials fixture 验证 managed 模式不向 run home 保留 RT、不反向覆盖 profile。
- [ ] `docker compose --env-file .env.example config` 或使用测试 env 验证 compose 变量。
- [ ] `cd cc2api && cargo fmt --check`
- [ ] `cd cc2api && cargo test`
- [ ] 如修改 cc2api Web 资源，运行 `cd cc2api/web && npm run build`；未修改则记录跳过原因。
- [ ] `git diff --check`（父仓与 cc2api 子仓）。
- [ ] 启动本地 orchestrator，验证 Accounts 页面单账号同步/绑定/调度状态与 Runs warmup badge。
- [ ] 跑一个真实或可控替身全链路：sync credentials -> 随机 topic -> queued/running -> terminal -> next time。
- [ ] 回归普通 task、batch、capture、continue、quota 和账号删除入口。

## 10. 回滚点

- [ ] cc2api endpoint 与 service 重构可独立回退，不改变既有网关请求契约。
- [ ] bench 功能可通过清空 `CC2API_BASE_URL` 停用；旧账号默认 `warmup_enabled=0`。
- [ ] 回滚时保留新增 SQLite 列和 warmup 历史，不做破坏性数据删除。
