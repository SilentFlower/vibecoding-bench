# 关联重授权与登录终端取证

## 基线

- 父仓 v3：`0ff97b1785c7d630000156f2e873547f68cd3701`；子仓 cc2api v3：`5af0c9f1d32e93245836d2a280fb6dd148499515`。
- 规划取证时未修改产品源码、未操作远端账号或服务；后续实现与验证见 implementation-state.md。

## 当前行为与缺口

| 证据 | 当前事实 | 对方案的影响 |
|---|---|---|
| `webui/app.js:211`、`orchestrator/main.py:7856`、`:8026` | 关联账号不显示重授权，start/commit 均拒绝绑定账号 | 不能只加前端按钮，需要新增受控的绑定重授权分支 |
| `orchestrator/main.py:7359` | 已绑定“同步到 cc2api”以绑定 ID 为准，最终从 cc2api 拉取凭据 | 不能把这个现有接口直接当作新登录凭据的推送入口 |
| `orchestrator/main.py:4475`、`:4590`、`:4746`、`:4808`、`:4832` | 登录会话按账号串行，force_reauth 使用暂存配置；提交会先覆盖真实 profile | 身份核对和远端提交必须先于真实 profile 覆盖 |
| `orchestrator/account_runtime.py:949`、`:1032` | v3 登录在固定容器独立 tmux 中运行；现有 commit_login 会把暂存 RT 写入主 HOME | 新绑定分支提交只能向主 HOME 发布 AT；RT 留在 cc2api 和受控管理 profile |
| `orchestrator/account_runtime.py:217` | ensure 只允许 active 的绑定 OAuth 账号 | 需要仅用于重授权的状态准入，不能放宽普通运行准入 |
| `orchestrator/account_runtime.py:480`、`:643` | 重授权使用排他租约，API 排空最多等待 120 秒，普通 CLI 是共享租约 | 保留现有调度区分；不能通过强行停掉活动 API 来开始登录 |
| `cc2api/src/handler/router.rs:666` | 通用 PUT 凭据走 config_permit/quiesce；带 status=active 时会早返回 enable_account | 通用 PUT 会冲突当前登录租约，也不能用它实现原子凭据导入 |
| `cc2api/src/service/account.rs:1522`、`:1588` | OAuth 串行锁实际为 CacheStore 的 `oauth:refresh:account:{id}`，不是进程内 refresh_locks | 导入应复用 Memory/Redis 两种锁语义；还需防锁 TTL 到期后的旧结果写入 |
| `cc2api/src/store/account_store.rs:350`、`:376` | token 与 auth_error 更新当前只按账号 ID 写入 | 延迟刷新成功/失败可能污染新凭据，需要按调用时凭据快照条件更新 |
| `cc2api/src/store/account_store.rs:451`、`:466` | 认证停用会设置 disabled、auth_error 与 disable_reason；通用 enable 会清除限流 | 如恢复认证停用，需有窄条件，不能直接套用 enable_account 清掉其他门禁 |
| `webui/app.js:660` | attachTerminal 仅建一次 WS，断线禁止输入但不重连；票据只生成一次 | 重连需要续取短票据、更新当前 socket 引用，并避免重复输入 |
| `orchestrator/main.py:7901` | v3 WS 只是 attach 现有 tmux；两个 pump 通过 gather 等待，错误被吞掉 | 网络断线不应取消 CLI；任一转发方向结束需收口另一方向与 Docker attach |
| `cc2api/src/service/runtime_bridge.rs:241` | 管理桥保留双向 WS，并每 3 秒验证管理会话 | 保持鉴权；退出或会话失效是终止条件，不能靠重连绕过 |
| `webui/index.html:519`、`webui/app.js:626` | 登录页面没有独立 URL 栏；粘贴授权码会添加本地终端回显 | 增加 URL 功能，去掉额外授权码本地回显 |
| `orchestrator/account_runtime.py:1172` | 重启时已有排他执行按遗留维护收口并释放租约 | 未确定结果的凭据导入需要持久标记，在完成对账前禁止自动释放门禁 |

## 规范约束

- `.trellis/spec/vibecoding-bench/backend/database-guidelines.md`：绑定 ID 权威、owner → profile 锁顺序、HTTP 在 DB 锁外、绑定唯一、旧回调不能污染新绑定。
- `.trellis/spec/vibecoding-bench/backend/account-runtime-v3.md`：绑定 RT 唯一刷新权归 cc2api；主 CLI HOME 只发布 AT；重授权排他，普通 CLI/API 独立；身份必须来自真实观测。
- `.trellis/spec/cc2api/backend/settings-database.md`：新增存储兼容 SQLite/PostgreSQL，迁移幂等。
- `.trellis/spec/vibecoding-bench/frontend/hook-guidelines.md`：attach/end 对称释放句柄，state 管理当前资源，避免重复事件与 socket。
- `.trellis/spec/vibecoding-bench/frontend/quality-guidelines.md`：零构建、中文交互、跨主题、窄屏、escapeHTML 与实际浏览器验证。

## 验证边界

- 有隔离 Docker、mock CLI、mock network 与真实浏览器的现成脚手架，入口位于 `deploy/v3/`。
- 模拟可证明导入、并发、断线、复制与持久恢复机制；不能证明真实 OAuth 成功或账号限制解除。
- `cc2api/src/service/oauth_flow.rs:18` 存在官方授权入口，但本任务继续让 CLI 生成实际链接，不调用管理端 OAuth 链接/换码实现替代 CLI。
- 当前部署用 HTTP；复制功能必须支持不依赖安全上下文的降级方式。
