# v3 登录草稿与授权终端设计

## 边界与已有模型

- 正式账号仍由 accounts 管理，保存后参与现有额度/任务/养号/cc2api 路径。草稿复用 account_environments 的 account_id=NULL 记录，不伪造正式账号 ID，不提前启用账号。
- LoginSession/AccountRuntime 当前负责内存会话、固定环境、同名占用和 tmux；开始登录早于账号提交。原状态接口和提交入口继续兼容，新增草稿管理是 v3 专属。
- 已有正式账号或同名软删除账号不是可彻底删除的草稿；account_id、同名 accounts、任务/运行历史、未确认提交记录任一冲突都阻止新草稿清理路径。

## 草稿状态与可见性

- 新增草稿查询及受控继续/重登/删除接口（以下为拟新增接口，不是现有能力）：GET /api/accounts/login-drafts；POST /api/accounts/login-drafts/{environment_id}/resume；POST /api/accounts/login-drafts/{environment_id}/restart；DELETE /api/accounts/login-drafts/{environment_id}。
- 草稿 DTO 明确区分 draft_id/environment_id 与正式 account_id；公开 name、generation、state、session_id、reconnectable、credentials_ready、container_status 和操作许可/说明。不得返回令牌、代理密码、发送器秘密或授权参数；浏览器从现有 status 获取当前链接。
- 正式 GET /api/accounts 和所有任务下拉保持既有语义；只有账号页合并展示独立草稿列表，用单独按钮和状态，禁用额度/养号/同步/任务等正式账号操作。
- 以 environment_id 固定资源归属；必要登录元数据持久化在 bench/login-drafts/<environment_id>.json（0600）。保存 sid、代次、阶段、CLI 版本和创建时间等可恢复信息，不保存 OAuth URL、授权码、AT/RT 或终端全文。代理继续从原固定环境私有配置恢复，不新增令牌副本。
- 列表兼容尚未有新标记的旧未关联环境：只在能证明无正式账号、历史和未知提交时视为草稿，否则显示需检查状态并限制删除。现有真实 10-13 草稿只作为取证对象，不在实现阶段自动删除。
- 建立 preparing → authorizing → ready_to_submit → committed 的可见过程；cancelled/ended/interrupted/reconcile/deleting 分别表示取消、终端结束、重启中断、需对账和清理未完成。状态由当前会话、实际凭据产物、持久标记和环境归属共同核对，不能只看凭据文件存在就宣称登录成功。

## 继续、重新登录与宕机

- resume 仅连接仍活跃的原 sid/tmux，复用原 CLI 与当前 status，每次 WS 重新取票据；刷新页面不重复启动 CLI、不重放任何输入。
- restart 是明确新授权动作：先确认旧登录已收口，再在原固定环境开始新 sid；清除旧 UI 链接和异步句柄，保留固定 HOME、设备身份、代理与版本选择。同名互斥覆盖开始、继续、取消、重登和删除。
- 宕机后管理服务仍按 unless-stopped 恢复，账号容器保持 restart=no、按需唤醒；不让全部账号随服务器自启突破容量。沿用启动 reconcile 收口遗留执行，草稿在列表显示中断/待提交。保留已写入产物，恢复时经实际 CLI 认证检查；不伪造原 tmux、SID 或仍有效的 OAuth 链接。
- 原关联账号有 pending login-commit.json 时沿用现有回执对账，不进入新草稿删目录路径。

## 完整删除与并发保护

- 用户已选择完整删除未提交草稿。页面明确确认：将取消该登录，并删除专属容器、未提交 HOME/缓存/暂存和该草稿专属 profile；已有正式账号及历史不受此动作处理。
- 全链按 owner → profile → environment 锁顺序，数据库写入使用已有 _db_lock；Docker/文件/HTTP 不占数据库锁。删除前重读环境 ID、代次、同名账号和历史引用，验证产品/部署/环境标签及目录 realpath，拒绝符号链接/共享归属冲突。
- 先持久记录 deleting，收口原会话和进程、确认租约/API/发送器空闲，再停止并移除唯一归属容器；清理仅白名单专属目录，最后条件删除环境/草稿记录。不能吞掉 IO 失败后返回成功。
- 记录位于环境目录之外，部分目录清理失败后仍能发现并重试；清理结果未知保留 deleting/reconcile，阻止同名新建、提交或重登穿过边界。重复删除幂等，已换代的旧请求不能删除新草稿。
- committed 和删除并发必须明确互斥；提交先成功时，新草稿删除接口拒绝处理已经成为正式账号的资源。

## 授权链接及终端状态

- 保留有界提取和 PKCE 校验，增加官方 CLI 2.1.293 已核对的精确主机/路径组合 claude.com + /cai/oauth/authorize；继续兼容 claude.ai/platform.claude.com + /oauth/authorize。不把主机、路径做宽泛匹配。
- 首张截图的旧屏幕已消失，必须以脱敏旧入口样本及当前真实 CLI 形状回归；不能只修新域名后宣称所有换行/状态问题已解决。ANSI、软换行、硬换行、完整 query 与截断均覆盖。
- 状态契约明确区分连接可重试、CLI/tmux 已结束、会话过期、提交待确认和凭据待提交；前端连接提示服从已确定的终态，禁止离线输入回调覆盖终态原因。
- 普通断线保持手动/有界自动重连。终态停止重连并显示原因和重新登录入口；已生成有效产物时按认证状态允许提交，不靠强行重新连接一个不存在的 tmux。

## 兼容及交付

- cc2api 子仓请求/凭据导入契约保持，不新增镜像、端口或外部服务；预计改动限于 orchestrator、webui、隔离验证、相关规范与当前任务记录。
- 新记录幂等兼容既有环境；回滚保留草稿元数据和目录，不通过恢复旧数据库覆盖最新凭据。已有已保存/关联账号删除策略继续遵守历史软删除规范。
- 实现只用合成数据和隔离 Docker/Chrome。真实生产登录及清理不在本阶段执行，后续 Git/发布/部署另按明确交付范围推进。
