# v3 授权码输入反馈与登录恢复 — 技术设计

## 1. 边界与已有入口

管理端保留真实 CLI 登录方式。新增浏览器输入和投递回执，授权码通过账号容器内原 tmux 的 stdin 路径提交，OAuth 交换继续由 CLI 完成。WebSocket 显示输出并保留同 SID 重连；v3 授权窗口不再同时通过终端发送键盘输入，避免两路授权码混入。旧版登录和续聊保持原交互路径。

相关现有定义：`LoginSession` 在 `orchestrator/main.py:4533`，`LoginManager.cleanup_reconciled` 在 `:5061`，`login_ws` 在 `:8425`；`AccountRuntime.begin_login` 在 `orchestrator/account_runtime.py:967`，`maintenance` 在 `:1206`。当前没有授权码投递回执字段或独立提交方法，以下接口均为拟新增，实施时先读取完整类和模型定义。

## 2. 输入与投递契约

### 2.1 拟新增管理 API

```text
POST /api/accounts/login/{sid}/code
  {request_id: string, code: string}
GET /api/accounts/login/{sid}/code/{request_id}
  -> {request_id: string, status: string, message: string}

status = sending | delivered | uncertain | rejected
```

- 使用既有管理鉴权与 `/accounts/` 桥接白名单，新增接口只针对 v3 活跃 authorizing 会话，响应 `Cache-Control: no-store`。
- `request_id` 为 32 位小写十六进制；授权码首尾去空白后为 1–8192 个字符，内部保持原样，拒绝 CR/LF/NUL/ESC 等控制字符，不猜测或补齐 code/state。
- 请求 body 上限 64 KiB；有界读取并校验，验证错误返回固定安全说明。不能让默认模型验证错误把原始 `input` 或授权码带进 422 响应。禁止输出请求正文及原始异常数据。
- 在现有 `LoginSession` 中增加有界回执集合，每 SID 最多接收 32 个不同标识，保存到会话结束；达到上限拒绝新标识而不淘汰旧回执。集合仅含状态和时间，不保存授权码。
- 投递前先登记 `sending`，同标识重复调用只返回已有回执，既不重新 paste 也不重复 Enter。确认注入完成为 `delivered`；可能部分完成或结果不可判定为 `uncertain`，明确未启动且拒绝为 `rejected`。
- 原会话消失、进程重启或回执不可查时只能显示结果未知，不推断“未发送”并重放。UI 保留该次请求标识用于查询，不保留授权码重试队列。
- 认证通过仍以既有真实 CLI 认证检查和 login status 为准，投递回执不能替代 `credentials_ready`。

### 2.2 投递到原 tmux

新增运行时投递方法，读取原执行证明并核对 login SID、环境、容器代次和执行 token，确认原 CLI 存活、没有进入保存/清理阶段。使用 owner → environment 锁序，Docker IO 不持有 SQLite 全局锁。

授权码只通过 Docker exec stdin 送到原 socket 上的 `tmux load-buffer -b <请求标识> -`，随后在同一原会话 paste-buffer 并发送 Enter。命令参数只含受校验的 SID/socket/请求标识，不包含授权码；临时 tmux buffer 在 finally 中删除。实现须验证 Docker SDK socket 的 EOF/收口与 tmux literal paste 行为，不落盘脚本或临时秘密文件。

锁内重新核对代次，串行保护同 SID 投递与取消/提交；任何可能已注入的失败都留 `uncertain`，不能因命令失败自动再次执行。`login_ws` 对 v3 授权码场景忽略/拒绝旧输入消息，输出、resize、心跳和重连保持原契约。

## 3. 页面状态与生命周期

- 登录 modal 增加密码输入框、显示/隐藏、字符长度、“发送到 CLI”按钮和独立发送状态。默认不自动显示授权码，允许原生上下文菜单粘贴。
- Enter 与按钮共用单一提交函数；同步设置发送中状态后才发请求，避免连点。与提交保存、取消、关闭互斥。
- 成功投递清空输入值，显示“已送到 CLI，等待认证检查”；未知结果清除输入值、保留请求标识并查询，禁止自动重发。被拒绝也不把原码保留在离线队列。
- WS 断线不阻止独立 HTTP 提交，但会话已结束、代次变化或服务端拒绝时停止发送；需要查看输出时仍可重连原终端。
- 句柄存 `state.accLogin`，迟到回包核对同一窗口/SID/代次；teardown 清输入、监听与定时器。取消结果未知仍按原契约保留诊断窗口，不假报成功。
- 更新 JS/CSS 静态版本，兼顾明暗主题和 390px 布局。纳入原焦点修正，同时确保旧版和续聊输入不受影响。

## 4. 草稿受控对账与代理摘要

### 4.1 拟扩展 DTO 与恢复接口

```text
draft DTO 新增：
  can_reconcile: boolean
  proxy_summary: string | null
  proxy_known: boolean

POST /api/accounts/login-drafts/{environment_id}/reconcile
  {generation: string}
```

代次输入继续使用现有草稿操作模型；响应沿用草稿刷新/现有成功形状。只有环境/name/草稿代次可核对、非 submitting/deleting、无活动作业/未知提交时提供 `can_reconcile`。列表获取 owner 锁失败仍返回只读快照，不阻塞或隐式维护；损坏/unknown 归属禁用恢复，仅提供查看环境。

恢复入口使用 owner → profile → environment 锁内重读归属与代次，再复用 `AccountRuntime.maintenance(..., "reconcile")`；已有正式账号、历史引用和未确认提交不能进入草稿恢复分支。恢复是停止并对账执行，不是删除 HOME 或清除授权产物。

现有 `cleanup_reconciled` 只按 `commit_context.environment_id` 找关联会话，需同时处理 `session.environment_id` 指向该环境的未绑定草稿。维护外层 owner 锁释放后，按现有要求重新进入收口，并核对原 SID/草稿代次/执行已停止，只释放该旧会话和其名称占用；新会话或代次变化立即拒绝，不能误清。恢复后列表重读状态，开放既有继续/重登/删除许可。

### 4.2 代理展示

从已核对的环境私有发送配置获取代理，生成仅 scheme/hostname/port 的摘要，IPv6 按地址格式处理，不返回 userinfo 或其他配置。`proxy_known=true, proxy_summary=null` 表示明确未配置；`proxy_known=false` 表示读取/归属无法确认。页面使用独立代理单元格，未知显示“配置待检查”。草稿仍不进入 `state.accounts` 或可执行账号集合。

## 5. 兼容、数据与已有改动

- 不需要变更 cc2api 上游发送/请求/TLS、OAuth 凭据同步 DTO 或数据库 schema。实施时确认管理桥允许新增路径；若事实不符，先更新设计再实现。
- 不保存授权码投递正文；现有草稿私有元数据不新增秘密字段。
- 纳入 baseline 中 `webui/app.js`、`webui/index.html`、`deploy/v3/verify_reauth_stack.py` 的焦点/提示/真实键盘验证改动。
- 保留 `.trellis/spec/vibecoding-bench/deploy/official-protocol-capture.md` 及两个旧任务目录的其他 22 项 baseline，不调整其内容或顺带提交。

## 6. 风险、验证与回滚

- stdin 已写入而回包丢失无法证明用户是否成功登录，因此必须保留未知状态，不能承诺所有失败都能安全自动重试。
- 新 UI 输入体验由真实 Chrome 验证，真实 CLI 隐藏输入由禁网 native 实验验证，完整成功链使用合成 CLI；不把这些替代真实账号 OAuth 全流程验收。
- 清理失败底层机制未确定，受控恢复不等于治理 Recorder 全部故障。
- 产品改动无需迁移数据库；回滚恢复上一版代码/镜像及静态资源，保留现有草稿和环境目录。上线前若有活动登录，核对状态并安排交接，不因更新自动删除或重登真实草稿。
- 最终检查覆盖授权码错误体、日志、argv 和 tmux buffer 清理。正式构建与发布沿现有 v3 双镜像 SOP，前端热补丁需固化到最终镜像；部署时旧服务保持运行。
