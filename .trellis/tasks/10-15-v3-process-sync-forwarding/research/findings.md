# 规划调查证据

## 代码事实

- `orchestrator/account_runtime.py:1787`：identity_import 读取实际 Linux/Node 基础环境，返回 canonical_env/canonical_prompt，没有进程数据。
- `cc2api/src/handler/router.rs:420`：CliIdentityImport 没有 canonical_process，创建账号初始化 `{}`。
- `cc2api/src/model/account.rs:379`：CanonicalProcessData 只有内存限制及 RSS/堆/外部缓冲区范围，尚无来源与采样元数据。
- `cc2api/src/model/identity.rs:571`：process_snapshot 根据范围及种子派生指标；`:721` 的 normalize_process 对未知范围给兼容默认值，不能用于宣称 v3 实测。
- `cc2api/web/src/components/Accounts.vue:965`：卡片直接格式化持久值，缺失时横杠。
- `orchestrator/main.py:8007`：已有绑定同步不再调用首次 create，不会补齐进程字段。
- `deploy/v3/verify_local.py:55`：真实网关配合手工 RuntimeHandler；向合成 TLS 发起连接后断开并断言 502，仅验证 ClientHello 和账号来源。
- `deploy/v3/verify_stack.py:143`：既有成功 SSE 是 runs-stream 管理消息，不能证明 messages 推理 SSE。
- `cc2api/src/service/runtime_transport.rs:175`：有配置时强制解析账号绑定并调用内部发送器；配置缺失但有部署 ID 时失败关闭。
- `cc2api/src/tlsfp/tlsfp.rs:315`：生产 rustls 根为 webpki_roots；`:437` 的额外根仅 cfg(test)。

## 线上只读结果

- 可见正式账号 1 个，10-15 已绑定网关账号 2，环境 stopped。
- 网关状态字段仍为 active，自动遥测和自动用量查询均关闭；active 不能推翻已有 account_on_hold 证据。
- 当前环境没有 `flows/api/observations.jsonl`，不能声称本次线上部署已完成真实 API 发送。
- 以上只读查询未唤醒账号、未调用上游。

## 决策

- RSS 必须来自官方 CLI 进程，静态 cgroup 配额独立显示；缺失明确未知。
- 首次创建和已有绑定补齐都纳入；普通旧画像保持兼容。
- 正式路由的完整本地 HTTPS 用测试专用信任根夹具完成，不能修改生产证书校验；另用当前生产发送器做真实公网非模型 HTTPS 核查。
- 真实推理缺可用账号，不以任何替代信号判通过。

## 首次创建配置核对

- `cc2api/src/handler/router.rs:390` 的 CreateAccountRequest 已支持 billing_mode、upstream_session_pool_enabled、upstream_session_pool_size、upstream_session_refresh_policy、concurrency、rpm_limit。
- `cc2api/src/model/account.rs:86` 的 BillingMode 接受 rewrite；当前普通账号默认 strip。
- `cc2api/web/src/components/Accounts.vue:1486` 的“仅属主刷新”对应 owner_only；用户所说“仅主属性刷新”按此已有选项落实。
- `cc2api/src/model/account.rs:12` 的 TTL 时长默认 60 分钟，用户仅修改刷新策略，没有要求修改该时长。
- 只在 `orchestrator/main.py:8057` 的真正 create_account 载荷设置六项；已有匹配和绑定不经过此创建分支。

## “同步”歧义调查

- `webui/app.js:235`：所有账号同名“同步”；`:311` 调单一入口，按 created 布尔值在结束后才告诉用户创建还是关联。
- `orchestrator/main.py:8007`：已有绑定直接解析原目标；未绑定时自动查找匹配，匹配不到才创建。随后 `_resolve_and_sync_cc2api_credentials()` 从 cc2api 解析权威凭据并写回本地，而不是把本地凭据重新上传给已有账号。
- `webui/app.js:406` 的 openWarmupModal 与 `webui/index.html:373` 的 select 将手动关联已有账号混在养号/额度配置里。
- 重新授权是独立登录/提交事务，已绑定成功后导入新凭据到原账号；不能把“更新进程指标”误接到该凭据写入路径。
- 用户回复“可以”确认四入口及创建/关联完全分开，随后完整 Brief 获得“确认”并已启动实施。独立动作、适用状态和异常结果均已落地；实际验收见 [verification.md](verification.md)。
