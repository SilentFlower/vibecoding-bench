# 代码证据与改造边界

## 基线与来源

- 规划日期：2026-11-03；父仓库分支 v3，已交付基线 9af2c121；cc2api 基线 1cc4168。
- 来源是当前对话、下列代码与已有规范。未执行真实账号解绑、刷新、重授权、迁移或部署。
- 保留工作区原有协议研究文档和 10-28/10-29 的无关任务目录；本轮规划只新增当前任务树材料。

## 现状

| 路径与定位 | 已确认行为 | 设计含义 |
| --- | --- | --- |
| orchestrator/main.py:9239 | create/bind/sync 共享关联函数；首次创建带 CLI 身份和默认配置 | 三种入口必须采用同一交接机制，不能只修新按钮 |
| orchestrator/main.py:9320 | 校验 active OAuth、身份、设备与绑定占用 | 保持身份与设备校验；暂停归属独立于人工停用状态 |
| orchestrator/main.py:9334 | 先从远端 resolve 并覆盖 profile，再提交关联 | 重绑时须先确认当前所有者，不能盲目拉取远端副本 |
| orchestrator/main.py:9639 | 解绑清关联并关闭旧养号调度 | 新协议接入现有入口，保留调度字段语义 |
| orchestrator/account_runtime.py:765 | 未绑定时优先已有完整 HOME；显式解绑交接完整 RT | 本地已独立轮换时不能回退到旧 profile |
| orchestrator/account_runtime.py:815 | 关联时 HOME/access 仅 AT；管理 profile 有完整镜像 | 交接确认后继续使用原秘密分布 |
| orchestrator/account_runtime.py:897 | owner_transition 用临时远端门禁、停止旧环境；不持久暂停远端账号 | 临时租约不适合代表长期本地所有权 |
| orchestrator/account_runtime.py:1129 | 未绑定作业收尾把完整 HOME 镜像回 profile | 重绑应读取同一当前来源，不从历史快照恢复 |
| orchestrator/main.py:6127 | 每 60 秒检查启用账号；绑定走远端，未绑定走本地刷新 | 本地后台、普通任务、两个迭代和手动刷新都需服从持久状态 |
| orchestrator/main.py:5585 | commit_bound 使用原绑定、临时登录、操作 ID、导入回执和恢复 | 复用已有关联重授权流程，不重新创建账号 |
| cc2api/src/service/account.rs:1872 | resolve_upstream_token 在 AT 不足 5 分钟时按需刷新 | OAuth 解析是集中检查点，但不能覆盖所有持有旧 AT 的发送 |
| cc2api/src/service/account.rs:1977 | 管理端 resolve 使用同一刷新锁；关联要求至少 2400 秒有效期 | 状态检查需要进入该锁并在提交时复核 |
| cc2api/src/service/account.rs:2024 | 导入按身份/回执/刷新锁校验，按条件恢复有限认证停用 | 可复用事务与回执原理；不能混淆人工停用 |
| cc2api/src/service/runtime_lease.rs:397 | begin_oauth_import 只接受 claimed、排他、同代 login: 租约 | 交接必须有独立受信任操作类型，不伪装登录 |
| cc2api/src/service/prime_poller.rs:433 | 预热先 resolve，再获取运行许可 | 只在实际发送前挡住请求仍可能已经刷新 RT |
| cc2api/src/service/telemetry.rs:542 | 后台会话持有 token，按时发送并派生异步发送任务 | 暂停必须覆盖旧会话、派生发送和在途排空 |
| cc2api/src/service/usage_poller.rs:35、cc2api/src/main.rs:220 | v3 关闭主动定时额度轮询；旧模式可按开关启用 | 保留模式差异；手工额度查询仍需门禁 |
| cc2api/src/handler/router.rs:1170 | 管理“测试账号”先拿 token，再主动请求 | 除模型请求外还须覆盖测试、额度、bootstrap 和其它账号上游活动 |

## 已有类型

- OAuthCredentialSnapshot：account_id、access_token、refresh_token、expires_at。
- OAuthCredentialImport：操作、身份、完整凭据和租约证明；定义位于 cc2api/src/model/account.rs:126。
- RuntimeGate：临时排他租约、API 活动计数、导入计数和持久租约文件。
- AccountStatus 仅有 active/error/disabled；没有长期本地所有权状态。
- accounts.cc2api_account_id 在解绑后变为 NULL，不能单凭此字段恢复原远端 ID 或证明当前刷新权。

## 验证基础

- orchestrator/test_deleted_binding.py：原 RT 交接、本地轮换保护、悬空绑定、落盘失败和重复收口。
- orchestrator/test_login_reauth.py：同 ID 重授权、身份冲突、响应丢失、部分落盘、重启和回执恢复。
- cc2api/src/service/account.rs、runtime_lease.rs 的测试：刷新锁、旧回包条件写入、导入与活动门禁。
- deploy/v3/verify_stack.py：已有 --browser --reauth、--browser --deleted-binding；新增交接场景应沿用随机部署、合成上游和精确清理机制。

## 规划结论

1. 持久所有权与临时租约分别负责长期归属、短期排空；旧状态或未知结果不自动超时放行。
2. 建立统一的账号上游活动许可，覆盖刷新前和实际发送前；遥测缓存 AT 也不能绕过。
3. 新建 CLI 账号、普通关联、兼容 sync 和 warmup 关联字段都要接入，避免形成旁路。
4. 刷新锁、代次条件写入、无令牌提交记录和幂等回执共同保护；只比较到期时间不足以选择 RT。
5. 状态迁移不得把人工/封禁/限流改成可用，也不能承诺本地模拟能证明真实 OAuth 可用。
