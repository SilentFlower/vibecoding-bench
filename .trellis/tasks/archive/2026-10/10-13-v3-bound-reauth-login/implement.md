# v3 关联重授权与登录终端实施计划

## 前置与评审

- [x] 检查现有 LoginSession/LoginManager、绑定 DTO/服务、Account、OAuth 刷新/存储、排他租约、WS 与 xterm 调用。
- [x] 建立 planning 任务并记录取证，保留原有无关工作区变更。
- [x] 将“仅恢复 OAuth 认证失效自动停用”的推荐策略写入最终方案，并收敛 PRD；与完整 Brief 一并评审。
- [x] 从最终三件套生成并完整展示 brief.md，用户已确认本任务规划。
- [x] task.py start；trellis-route 命中个人 inline 默认，已加载受影响层 trellis-before-dev 规范。

## 实施顺序

1. cc2api 凭据原子导入与回执。
   - [x] 在 handler 定义受控 DTO/路由，验证 admin/service 鉴权、有效登录排他租约与身份。
   - [x] 在 service 复用现有 OAuth 锁，store 同事务保存凭据/回执，仅恢复明确 OAuth 认证失败停用，保留其他策略和限流。
   - [x] 增加 SQLite/PostgreSQL 幂等回执表与只读对账入口，不新增令牌副本。
   - [x] 刷新成功/失败和相关认证状态写入增加调用时凭据条件，覆盖锁 TTL 到期后旧回包。
2. bench 绑定重授权。
   - [x] 扩展 LoginSession 明确记录绑定、环境、租约与提交阶段；放行仅 v3 的显式 force_reauth。
   - [x] 仅重授权允许读取非 active OAuth 配置；普通执行继续拒绝。
   - [x] 暂存登录配置移除旧 OAuth 身份与凭据，保留设备配置；提交前校验真实新身份。
   - [x] 按 owner → profile 锁顺序导入、镜像管理 profile、主 HOME 仅发布 AT，保留绑定/环境/养号/限流/阈值策略。
   - [x] 持久记录不确定提交，重试/取消/TTL 清理/启动对账不丢凭据，不提前释放维护门禁。
3. 登录连接与链接体验。
   - [x] 实现有界 tmux 链接读取及 no-store 会话状态接口；先验证支持 CLI 输出，不替代 CLI 授权。
   - [x] WS pump 首个结束收口另一个，Docker 阻塞操作不占事件循环；断网仅 detach。
   - [x] 增加授权链接栏/复制/打开、连接状态、手动重连与自动有限重试，每次续取票据。
   - [x] 更新当前 socket 引用与代次、心跳、输入门禁；不重放输入，去掉授权码额外本地回显。
   - [x] modal 关闭/取消/过期/commit 后清理全部新句柄；静态资源版本与明暗主题/窄屏同步。
4. 验证、规范与交付。
   - [x] 完成定向单测和隔离 Docker/实际浏览器验证。
   - [x] 走 trellis-route(target=check) → Check-All，修复并复查发现。
   - [x] trellis-update-spec 更新绑定重授权、唯一刷新权、提交恢复与终端生命周期契约；六份既有规范/索引已写入并核对。
   - [x] 展示并确认父/子仓精确提交范围与验证证据；两仓业务提交已推送，helper 已写入 completed + Close，任务记录纳入独立提交；生产部署另行安排。

## 验证命令

```bash
python3 -m unittest discover -s orchestrator -p 'test_*.py'
python3 -m unittest discover -s deploy/v3 -p 'test_*.py'
node --check webui/app.js
git diff --check
```

```bash
cd cc2api
cargo fmt --check
cargo test
```

- 如果改变 cc2api 嵌入前端资源或前端构建输入，追加 `cd cc2api/web && npm run build`；当前不计划改 Vue 管理页面。
- 复用 `deploy/v3/run_local_verification.py`、`verify_stack.py` 与 `verify_browser.py` 的专用随机部署和内部 mock 网络；新增场景脚本名称在实现时确定。
- 只使用合成凭据；fixtures 不进入产品镜像，不请求真实模型、修改真实账号或重启旧服务器服务。

## 场景—路径—期望

| 场景 | 路径 | 期望 |
|---|---|---|
| 原关联账号重授权 | 页面 → start → CLI → commit → cc2api DB/profile/HOME | 同一账号 ID 与环境；管理 profile 新 AT/RT，主 HOME 只有 AT；请求使用新凭据 |
| 非 active OAuth 重授权 | disabled/error 配置 → 登录准入 → 导入 | 可以修复凭据，普通 CLI/API 准入仍遵循状态；只恢复明确 OAuth 认证失效停用 |
| 错登、组织冲突、新身份缺失 | 暂存文件 → commit | 写远端/profile 前拒绝，原绑定/凭据保持 |
| 活动 API/CLI | start → 原排他租约 | 正式 CLI/续聊拒绝；API 排空/超时不截断 SSE；其他账号正常运行 |
| 双提交与绑定变化 | 同 sid 并发/重试、原绑定被改 | 幂等；绑定变化/旧代次冲突，不能写其他账号 |
| 旧刷新延迟回包 | mock refresh 暂停 → 导入 → 旧成功/失败返回 | 新凭据/认证状态不被旧结果覆盖；Memory/Redis 锁语义一致 |
| 导入响应丢失 | 远端已事务提交 → HTTP 超时 → retry | 回执证明结果，返回当前凭据，不重放已过时 RT |
| 本地落盘/清理失败 | 远端成功 → profile/HOME/cleanup 故障 | 明确待重试/对账，暂存不丢、门禁不提前放行 |
| 中途服务重启 | 导入前/后断点 → 启动对账 | 结果未知保持隔离；确定后同步权威快照、清理并释放 |
| 手动停用、额度等待、关闭养号 | 重授权前后比对状态 | 保留人工策略、限流、观察与阈值等待；认证恢复不自动重开养号 |
| WS 断线/半开/票据过期 | 浏览器 → 管理桥 → WS → 同 tmux | 状态明确、重新取票据、重连同一会话，不重复登录和授权码 |
| 断线时已输出 URL | tmux 输出 → 状态 HTTP → 页面 | 完整 URL 可见，不依赖首次 WS 数据；不缓存终端全文 |
| ANSI/换行/恶意 URL | mock pane → URL 提取 → DOM | 官方完整链接正确；无效、非 HTTPS、超长、恶意链接拒绝/XSS 不执行 |
| HTTP 复制/窄屏/主题 | 真实浏览器 390/1280、明/暗 | 复制或明确可选中手动复制；按钮和全文可访问，无页面挤压 |
| 取消/关闭/过期/退出 | 生命周期收口 → 旧 WS/ticket/输入 | 无重连/心跳泄漏；过期、撤销会话和非法票据拒绝 |
| 旧功能回归 | 未绑定登录/取消、续聊终端、普通并行 API/养号 | 原行为保持；旧部署不放行绑定重授权 |

## 风险文件与回滚点

- 重点：`orchestrator/main.py`、`orchestrator/account_runtime.py`、`webui/{app.js,index.html,style.css}`、`cc2api/src/{handler/router.rs,service/account.rs,store/account_store.rs,store/db.rs}`；认证状态条件若涉及调用方，只修改保证同凭据快照的一小段，不改变上游重试协议。
- 先完成 cc2api 导入/对账契约再接 bench 调用，不发布单侧已放行却缺少另一侧导入能力的版本。
- 发布/回滚前确认无待提交重授权、导入回执可对账、租约已收口；回滚不删除账号凭据和新增回执表。
