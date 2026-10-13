# 实现过程记录

## 授权与路由

- 用户已确认完整 brief；任务已进入 in_progress，父/子仓均在 v3，不重新询问规划确认。
- implement 路由由 `route_state.py resolve --target implement` 命中：inline、source=route-prefs；当前 session 已记录该任务路由。
- 不允许主动派发子代理；本次按 inline 执行。check 仍须在完成 focused validation 后进入 trellis-route(target=check)。
- 本轮实现不包含提交推送/生产部署；旧服务器服务未操作。

## 已写源码

- cc2api：受控 OAuthCredentialImport、管理 POST import/GET receipt、同 OAuth cache lock 导入、SQLite/PG 共用增量回执表、凭据与状态同事务、仅恢复认证停用、保持限流。
- RuntimeGate：导入占用计数、阻止提前 release、新 fence 操作取消迟到导入权限；snapshot 额外返回 importing。
- OAuth：刷新成功/失败/缺少 RT 的写入均按调用时 AT/RT 条件更新；永久凭据失败停用也按原快照写入，防迟到回调停用新凭据。
- bench：允许 v3 显式绑定重授权，固定环境暂存 HOME 去除旧 oauthAccount，验证新 UUID/邮箱/组织，持久提交意图后同步同一 cc2api ID；管理 profile 有 RT，主 HOME 只发布 AT，设备字段与额度/开关保持。
- 部分失败：回执重试、取消与重启对账；结果未知保留暂存/维护门禁；对账先 fence 后 stop/query，镜像已提交结果并销毁暂存，再释放。
- 环境页 reconcile 可收口待提交登录，并清理旧 LoginManager 占用/保存幂等结果。
- 终端：login_terminal.py 有界官方 URL 提取、status no-store、Docker 调用移至线程、sock_sendall、FIRST_COMPLETED 收口；WS 断线仅 detach。
- UI：独立链接栏和 HTTP 复制降级、状态/自动手动重连、每次续取票据、心跳/有限重试、连接代次、禁止离线输入重放、取消先等待后端确认、清理定时器/socket；去掉授权码额外回显。

## 已有证据与正在运行

- 初版 `cargo check --tests --locked` 已通过；已有 4 项新增 Rust 定向测试通过。
- `/tmp/v3-reauth-rust.log`：一次全量 Rust 测试已通过（最后有 Doc-tests 完成），之后新增永久凭据停用条件方法，需再验证。
- `/tmp/v3-reauth-python.log`：165 项全量 Python 测试通过（74.554s）；之后新增环境页对账收口，需再验证。
- `/tmp/v3-reauth-python-focused.log`：最初 9 项登录定向通过。
- 运行单测必须使用已有 `/tmp/v3-verify-venv/bin/python`，系统 python 缺 docker。venv 已有项目依赖，不需要修改全局环境。
- 新测试 `orchestrator/test_login_reauth.py` 目前覆盖 URL、错登、响应丢失、部分落盘、重启对账、未知结果隔离、半开 WS、普通非 active 拒绝以及环境页维护收口。
- 最近源码修改后需要重新跑 focused/full；不能把旧日志当作最新代码全部通过。

## 剩余工作

- 阅读并验证目前差异；真实 CLI 支持版本的 URL/state/redirect 形状仍需核对，不能将合成 URL 样本当作真实 OAuth 验证。
- 前端待补生命周期边界：取消时 poll 可能提前 return 导致失败后不继续轮询；关闭/提交并发及 vendor 加载等待应有界。当前 syntax 已通过一次，最新修改还需检查。
- 当前 bound session cleanup/maintenance/reconcile 多路径需实际容器场景验证，尤其 heartbeat/门禁、释放失败、已确定未提交的旧页面提示。
- 完成新 fake CLI 可控授权输出及本地真实镜像/UI→API→DB 测试，生成任务报告与截图，清理只属于随机验证部署的资源。
- 进入 Check-All（路由 helper 默认优先），修复并复查所有 CHK/FBK，更新相关规范；提交前按精确范围审批。

## 本地镜像与验证入口

- 现成基线清单 `/tmp/v3-warmup-c.json`，镜像 `vibebench-v3-{control,account}:v3-local-warmup-20261013-c`。
- 官方本地 build：`python3 deploy/v3/manage.py build --release <全新唯一批次> --manifest <新文件>`，会冻结当前源码、两镜像同批，dirty 工作区仅用于本地验证，不能 publish。
- Dockerfile 实际路径 `images/v3/Dockerfile`，backend stage Rust 1.96 bookworm，control/account 两个最终 target。`COPY orchestrator/*.py` 会纳入 login_terminal.py。
- `deploy/v3/verify_stack.py` 为实际 Compose、HTTP/SSE/WS/退出、旧哨兵验证脚手架；`verify_browser.py` 用独立 Chrome/CDP；mock_network.py 为内部 SOCKS/DNS/HTTP 替身。
- trellis-run-full-chain 已完整读取；已有 implement.md 场景表并经本任务规划确认，继续在已确认范围内执行，不再要求选场景。当前无 e2e-playbook；其新增 diff 可留到最后评审，不因知识沉淀中断实现。

## 工作区保护

- 原无关修改 `.trellis/spec/vibecoding-bench/deploy/official-protocol-capture.md` 与两份旧未跟踪任务目录保持，不能混入本任务提交。
- 不 prune Docker，不使用宽泛容器清理，只删除验证脚本随机部署的精确 labels。


## 最终实现与检查证据（2026-10-13）

- 最终产品补充：gateway 与 prime poller 的迟到 OAuth 401 按实际失败 AT 和当前 AT/RT 条件停用；prime 失败 AT 仅内存保存，不进日志/回执。认证恢复也识别已有 prime OAuth 401 分类。
- 全面检查发现并修复：环境页对账与提交未共用账号锁；维护入口现按 owner → profile → environment 排序，cleanup_reconciled 在非重入 owner 锁外调用。并发请求用例已通过。
- 前端收口补充：启动 HTTP 未返回时关闭窗口先等待 SID，再确认取消；取消失败保留窗口供重试。终端加载有界、提交与关闭互斥、取消失败后继续轮询。终端区域可滚动，避免提交按钮被裁切。
- 本次 Check-All 为 inline / interactive / requested=auto / effective=full；依据公开 API、schema、并发状态与跨层凭据归属变化。既有规范已按 manifest、路由结果读取；未做生产操作。

### 实际执行

| 独立验证 | 结果 | 本地日志 |
|---|---|---|
| /tmp/v3-verify-venv/bin/python -m unittest discover -s orchestrator -p test_*.py | 168 通过；47.323s | /tmp/v3-reauth-python-reviewed.log |
| /tmp/v3-verify-venv/bin/python -m unittest discover -s deploy/v3 -p test_*.py | 29 通过 | /tmp/v3-reauth-deploy-tests.log |
| cc2api cargo test --locked | 638 通过（577 单元 + 61 集成），1 个已有 ignored | /tmp/v3-reauth-rust-last.log |
| node --check、py_compile、cargo fmt --check、父/子仓 diff --check | 通过 | 已有实际命令输出 |
| run_local_verification.py | 通过：账号原生 TLS、API/CLI 长流并行、取消、Recorder 故障和重启对账、固定身份 | /tmp/v3-reauth-local.log |
| verify_stack.py --browser --reauth（最终批次） | 通过：UI + HTTP/WS + 实际 tmux + 双 DB/凭据文件 | /tmp/v3-reauth-stack-final.log |
| 两镜像联合本地构建 | 通过；未发布 | /tmp/v3-reauth-build-f.log |

### 真实跨层场景

| 场景 | 路径 | 期望 | 结果 |
|---|---|---|---|
| S1 原关联重授权 | Chrome → HTTP/WS → tmux → 双 SQLite/profile/HOME | 原 ID/容器/userID，权威新 AT/RT，主 HOME AT-only，保留策略与限流 | 通过 |
| S2 断开/手动重连/离线输入 | Chrome → 新 ticket → 原 WS/tmux | 原 SID，不重复登录，不重放离线输入 | 通过 |
| S3 HTTP 链接和四种布局 | 非安全 HTTP 域名 → status/pane → DOM | 完整 URL；打开参数正确；选中复制降级；1280/390 明暗，提交按钮能实际点击 | 通过；打开外页被测试拦截，不访问真实 OAuth |
| S4 错登与取消 | HTTP → 真实合成 CLI → 双 DB/暂存 | UUID 不符拒绝；原凭据和回执数保持；取消清理 | 通过 |
| S5 启动期间关窗 | UI → start → cancel → 租约/暂存 | 收到 SID 后确认取消，窗口才关闭，无隐藏占用 | 通过 |
| S6 鉴权与退出 | UI/HTTP/WS → 会话/票据登记 | 内部证明不能仅用管理密码代替；非法票据拒绝；旧 cookie 不可重放 | 通过 |
| S7 普通执行与旧哨兵 | API/CLI/容器 → 观察/DB → stop/backup | 普通并行机制保持；原哨兵进程及文件 hash 不变 | 通过 |

- 导入响应丢失、profile/HOME 部分写入、无内存会话的重启恢复、未知结果隔离、身份缺失/邮箱/组织冲突及绑定变化，由真实临时 SQLite/文件和明确的远端/Docker 替身单测覆盖；不冒充全部已做浏览器故障注入。
- 已核对官方 npm 固定版本 2.1.280 与 2.1.293 的原生包内链接生成代码：32 字节 base64url state 与 S256 challenge（43 字符），手动 redirect 为 platform.claude.com/oauth/code/callback。未运行真实登录、读取真实 HOME 或输出实际授权 URL。
- 官方 native 包 SHA256：2.1.280 = 3d95573100e302f79d536ef3eb64f5da0d537433af6ae8de571dfeda6d52bfd3；2.1.293 = 7b6d6842a9e9de1fa0f5dfc18967696b91883b9d82be333a05b35bcf21f7d70f。来源为 registry.npmjs.org 的对应固定包。

### 数据和资源恢复

- 最终随机部署 stack-verify-7693022ef7 的全部容器及网络已删除，Docker label 查询为空；临时两侧数据库、合成账号、凭据/回执、测试 Chrome 配置随 TemporaryDirectory 清理。
- 旧哨兵 StartedAt 与数据库文件 SHA256 前后相同。原已有 Docker 服务未操作；本轮无 SSH、真实账号、生产发布或部署。
- 无未恢复业务数据、不可逆外部副作用或用户需处理的善后。保留本地验证镜像/清单和 /tmp 截图日志供审阅。
- Playbook 尚无既有文件。本轮新常量/可复用入口留在上述受控验证代码和任务记录；新增 spec/playbook diff 在后续规范更新阶段评审，不自动创建。

### 交付边界

- 规范更新及两仓业务提交推送已完成，helper 已写入 completed + Close；当前任务记录以独立提交发布。生产部署尚未执行。
- [上线后验证] 用户安排可用测试账号后，用真实 CLI 走同一重授权并确认正式 API；合成通过不证明上游 OAuth 成功或账号限制解除。
- SQLite 迁移与 store 事务已实测，PostgreSQL SQL 兼容按既有规范人工核对；未对现有 PostgreSQL/Redis 服务做业务写入。

- 最终本地清单：/tmp/v3-reauth-f.json；批次 local-reauth-20261013-f；dirty_worktree=true；冻结源码 SHA256 76806197aa8a86f247c389833abb56f124b8d11fb17be64b0ded1d045ba8c6d5。

- 已有 PostgreSQL profile 集成用例 postgres_profile_settings_and_rollback 因未配置独立临时 DSN 保持 ignored；不是本次 OAuth 导入失败。
- 最终修复后复查：没有剩余 CHK/FBK；既有任务文档状态和取证时点作事实同步，不改变 PRD 需求/设计。用户已确认精确提交计划，两仓业务推送成功。

## 规范更新与提交预检（2026-10-13）

- Update-Spec 结果为 written：更新 cc2api service-architecture、bench account-runtime-v3、frontend hook-guidelines 与对应三份索引，共六份既有文件；未新增规范路径。
- 规范覆盖凭据导入与回执、租约 fence/pin、迟到回包条件写入、提交恢复、固定环境凭据归属、终端重连/链接/取消生命周期；已反查现有方法、DTO 字段、六段结构、链接锚点和 diff 空白。
- Update-Spec 阶段仅六份规范变化，产品源码与最终检查基线一致；进入 Push 后仅同步当前任务的既有记录，无需重跑产品测试。
- 两仓已 fetch origin/v3；ahead/behind 均为 0/0，暂存区为空，无冲突或未完成集成状态。计划按 cc2api → vibecoding-bench（含新子模块指针）→ 当前任务记录顺序提交推送。
- 父仓现有 v3-build.yml 对每次 v3 push 自动联合构建并发布两个 GHCR 镜像；业务与任务记录两次推送会触发两批构建，生产部署不由此自动执行。
- 原有 official-protocol-capture.md 和两份旧任务目录保留原状，不进入本次提交。

## Git 交付与完成态（2026-10-13）

- 用户确认一次精确计划后，先提交并推送 cc2api，再提交并推送 vibecoding-bench；父仓提交包含已推送的子仓指针。业务提交分别为八个和十九个确认文件。
- 两仓业务推送全部成功后，task_progress.py write --complete 原子写入最终进度、completed、completedAt 与 Close；返回 closeResult=closed，无 closeBlockers。
- 当前任务的九个既有文件组成独立任务记录提交；未新增记录路径、修改其他任务或执行物理归档。
- 业务推送的 GitHub Actions 联合构建已确认启动；GHCR 是否发布成功须以该批构建最终结果为准。服务器旧服务未操作。
