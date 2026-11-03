# 实施与验收计划

## 顺序与责任

本子任务 A 先于子任务 B 实施，无需依赖 B 的 UI。主体实现和聚焦验证已完成；父任务负责最后联合验收和同批部署。

1. [x] 进入实施前加载 trellis-before-dev，记录父仓库/子模块基线，保留原无关脏文件；读取现有实体、DTO、存储方法和全部调用方。
2. [x] 完成新增所有权/回执模型及 SQLite/PostgreSQL 幂等迁移，定义操作方向、协议版本、代次条件、可信来源和错误；不扩展普通配置写入白名单。
3. [x] 实现统一上游活动许可与排空，覆盖模型、count_tokens、bootstrap、预热、额度、测试、遥测缓存 AT/派生发送、OAuth resolve/refresh/401。
4. [x] 实现远端受信任交接 prepare/commit/status 及同代条件事务；沿用内部服务鉴权，保持现有重授权导入语义。
5. [x] 实现本地归属/待办及 gateway→local、local→gateway 协调，接入 create/bind/sync、旧 warmup 关联、解绑与远端明确删除收口。
6. [x] 统一已关联重授权的持久维护阶段及恢复；本地调度/任务/两迭代/重新登录统一读取归属，防止空关联降级。
7. [x] 处理旧记录及协议能力不匹配；补齐两端脱敏状态展示、只读列表和可执行恢复入口。
8. [x] 按下表完成聚焦测试，再运行规定整体验证；完成 Check-All 后同步规范，提交子模块再提交父仓库。

## 验证计划

| 层次 | 命令或入口 | 核心证据 |
| --- | --- | --- |
| Python 聚焦 | cd orchestrator 后 python -m unittest test_deleted_binding test_login_reauth test_credential_publication test_account_runtime test_main | 本地真实 SQLite/文件、完整 HOME、兼容入口与故障收口 |
| Python 全量 | 在现有依赖环境运行 python -m unittest discover -s orchestrator | 原任务/迭代/额度/登录回归 |
| Rust | cd cc2api 后 cargo fmt --check、cargo test | 持久代次、全入口门禁、回执、迟到写入、普通账号兼容 |
| 数据库 | 新增迁移及事务分别在 SQLite、可用的隔离 PostgreSQL 运行 | 幂等迁移、条件写入失配与回执原子性；环境缺失如实报告 |
| 前端 | 变更 cc2api 前端时 cd cc2api/web 后 npm run build；原生 WebUI 用 node --check | 脱敏展示、无秘密字段、原普通配置可编辑 |
| 既有隔离场景 | verify_stack.py 的 --browser --reauth 与 --browser --deleted-binding 分别运行 | 原关联重授权、悬空解绑能力保留 |
| 新增隔离场景 | 在 deploy/v3/ 下扩展正式验证入口，先提供 --help 再记录精确命令 | 随机部署、真实 HTTP/DB/容器、合成 OAuth、各入口连接计数 |

不得把尚未新增的验证参数写成已经存在或已经执行的命令。

## 必测场景

- [x] 正常创建首次绑定；创建远端成功而本地失败，双端保持单一所有者；首次关联远端权威账号不上传本地旧凭据。
- [x] 正常解绑、已有/等待请求收口、长期本地连续轮换后关联原 ID。
- [x] dormant 账号的模型/count_tokens/预热/额度/测试/遥测/辅助请求和刷新均零上游连接；其他账号继续正常。
- [x] 在多个入口同时争抢时，暂停账号不会被粘性会话跨号重试绕过。
- [x] 新目标不存在、身份/设备/环境冲突、重复绑定、远端明确删除分别保持正确拒绝/收口。
- [x] 关联重授权成功、取消、错账号、人工停用、认证自动停用及限流。
- [x] 每个交接边界的响应丢失、部分落盘、重启、租约过期及迟到回包；回执未知时保持维护。
- [x] 新旧协议不匹配时明确拒绝绑定变更/危险回退；既有普通账号保持兼容。
- [x] HOME、设备、缓存、会话、配置、计划及数据库逻辑事实前后核对；日志和回执无秘密。

## 风险文件与恢复点

- 主要文件：orchestrator/main.py、account_runtime.py；cc2api/src/model/account.rs、store/db.rs、store/account_store.rs、service/account.rs、runtime_lease.rs、gateway.rs、telemetry.rs、prime_poller.rs、usage_poller.rs、handler/router.rs。
- 新增存储模块可按现有分层集中所有权与回执职责；不能扩展成无关调度重构。
- 页面与验证：webui/app.js、cc2api/web/src/components/Accounts.vue 及其已存在的类型定义；deploy/v3/ 相关验证入口与交付预检。
- 恢复原则：保留当前凭据和无令牌 pending，先查远端回执；没有有效回执不释放维护，不用历史快照覆盖。

## 完成门槛

- OA1–OA7 有逐项证据，未知/跳过项目明确记录。
- Check-All → Spec 更新 → 提交/推送遵守当前流程；不包含原无关脏文件。
- 本子任务验证结束后进入子任务 B；最终上线由父任务统一核验两个子任务和同批清单。
