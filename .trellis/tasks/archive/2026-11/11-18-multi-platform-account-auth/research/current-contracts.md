# 多平台账号与授权的现有合同

## 任务归属

父任务为 `../../11-18-multi-platform-account-runtime/prd.md`。凭据研究任务已 completed + closed，统一合同为 `../../11-18-agy-managed-credential-contract/research/credential-contract.md`。本任务当前处于 planning。

## 网关账号与迁移

- `services/gateway/src/model/account.rs:170` 的 Account 包含 auth_type、AT、RT、expires_at、账号身份、代理、request_backend 和策略；当前缺少账号平台字段。
- `services/gateway/src/model/account.rs:116` 的 AccountAuthType 为 SetupToken / Oauth，默认 SetupToken。OAuth 与账号平台属于不同维度。
- `services/gateway/src/store/account_store.rs:251` 按 email 判断重复，当前去重条件缺少平台维度。
- `services/gateway/src/store/account_store.rs:1038` 的 list_filtered 在 SQL 中完成搜索、状态筛选、计数及分页。平台筛选应进入同一查询边界。
- `services/gateway/src/store/account_store.rs:1101` 的 list_schedulable 以 active、限流状态筛选，当前缺少平台隔离。新增 AGY 账号须防止误入既有 CC 调度、刷新、额度及遥测路径。
- `services/gateway/src/handler/router.rs:901` 的 request_backend 校验只接受 legacy / native293；正式 AGY 业务运行由运行环境子任务承接。
- 迁移台账当前有 gateway.baseline.1、proxies.2、proxy-sync.3、session-policy-blocks.4。新结构使用后续登记步骤，并同步执行分支、冻结定义来源映射和演练。既有冻结基线保持原摘要。

## 授权、凭据回传与兼容边界

- `services/gateway/src/service/oauth_flow.rs` 的 GenerateAuthUrlRequest 接受代理选择，OAuthSession 保存 state、PKCE verifier、scope、代理及创建时间，TTL 为 30 分钟，当前为 CC 专用。
- `services/gateway/src/service/oauth_flow.rs` 的 ExchangeCodeResponse 明确包含 access_token、refresh_token、expires_at、账号 UUID、组织 UUID 与 email_address。
- `services/gateway/src/handler/router.rs:1777` 的 oauth_exchange_code 将该响应直接返回管理客户端。
- `services/gateway/src/handler/router.rs:405` 的 list_accounts 将 Account 序列化到分页列表；`:916` 的 get_account 直接返回 Account。
- `services/gateway/src/service/account.rs:1077` 的 get_account 返回存储对象；`:1101` 的 list_accounts 返回完整存储账号。
- `apps/web/src/api.ts:54` 的 Account 声明完整凭据字段；`:273` 的 OAuthExchangeResult 声明 AT/RT；`:648` 的 exchangeCode 消费授权交换接口。
- `apps/web/src/components/Accounts.vue:890` 的 exchangeOAuthCode 接收凭据，`:902` 附近的 applyOAuthResult 将凭据写入新建表单。
- 已核对现有接口会返回完整凭据。用户已确认本轮复用现有链路，通过平台适配接入 AGY；CC 既有接口及凭据返回保持兼容。父需求 R02 已同步这一边界。统一收口作为独立议题。

## 刷新与所有权

- `services/gateway/src/service/account.rs:2105` 的 resolve_oauth_credentials 沿账号刷新锁处理权威快照。
- `services/gateway/src/service/account.rs:2452` 的 refresh_oauth_account 使用现有 CC OAuth 刷新实现；AGY 须按平台分派。
- `services/gateway/src/store/account_store.rs:631` 的 update_oauth_tokens_if_current 提供旧凭据条件更新参照。
- `services/gateway/src/handler/router.rs:1506` 的 resolve_oauth_credentials 交付受信内部凭据；公开状态与私有快照需按调用方权限区分。
- 共同所有权及锁序由 account-runtime-v3 与 service-architecture 持有。AGY 的字段、身份与原生缓存边界采用凭据研究合同，避免套用 CC UUID/组织语义。

## 原生 AGY 授权依据

- 已有私有研究脚本 prepare_login.py 使用固定 1.5.9 原版、UID1001、独立 HOME、只读执行体、cap-drop ALL、no-new-privileges 和 `ANTIGRAVITY_REMOTE_OOB_AUTH=true` 启动原生交互 CLI。
- read_login_url.py 从原生终端取得 accounts.google.com 授权 URL，校验 PKCE S256、response_type=code，redirect_uri 为 `https://antigravity.google/oauth-callback`。
- submit_code.py 将用户提供的一次性授权码送回同一原生交互终端，凭据保存在该私有 HOME。
- 本轮使用独立临时 HOME 与执行副本读取原版帮助，结果显示通用 CLI 入口及模型等子命令；帮助列表没有专用 auth 子命令。登录驱动应使用已验证的原生交互/OOB 入口。
- 上述过程没有本轮真实授权或模型调用。真实浏览器授权需要用户参与；原有 8 次模型预算已使用全部预留。

## UI 与验证入口

- Accounts.vue 已使用 ChoiceSelect、NumberInput、InfoTooltip，授权流程为 generate / exchange / done；关闭与卸载递增 oauthGeneration 并取消旧请求。
- 平台切换、账号切换、取消授权及迟到回包应复用原代次隔离。账号表单轮询期间保持草稿、焦点和当前选择。
- 账号 UI 验证入口为 deploy/flower2api/verify_accounts_design.py；整体回归包含 verify_management_ui.py、verify_management_polish.py。
- 网关规范要求 cargo fmt --check 与 cargo test --locked；前端构建运行 npm --prefix apps/web run build；数据库定义及迁移演练按对应平台规范执行。

## 已收敛的设计依据

- 用户明确的方向为复用现有账号、授权和凭据管理链路，增加平台维度及 AGY 适配。既有 CC 工程/养号链路使用的管理接口保持兼容。
- 冻结基线 accounts 表的 email 为普通非空列，当前重复校验来自 AccountStore::create_with_ownership。平台去重可通过新登记迁移补充平台维度约束，保留原表与 ID。历史重复数据须在迁移前检测并报告。
- CredentialIdentity 的现有协议包含 environment_id、bench_account_id、device_id、account_uuid，属于 CC 运行环境交接证明。AGY 独立授权使用真实已认证身份，避免伪造这些工程绑定字段。锁、CredentialGate、权威 accounts 存储和 CAS 规则继续复用。必要的 AGY 操作元数据在追加迁移中保存，元数据只保存归属、代次、操作和阶段。
- 现有列表调用方包括 Cc2ApiClient.list_accounts。其缺省调用保持 CC 视图，新管理页显式查询全部平台，防止旧绑定流程误取 AGY 账号。
- 原生授权及刷新适配依赖镜像内固定原版制品。构建准备沿现有 staging 方式增加固定身份校验，原版二进制留在私有制品输入中。该制品准备属于本任务的授权依赖，正式业务 worker 池由运行环境任务承接。
