# 远程凭据交接的下一实施边界

## 已核对的实际入口

- `CredentialOwnership.associate/resume/detach/retire/_clear_missing_binding`持有原名称owner锁，长期协议仍由原`account_credential_ownerships`及Gateway回执管理。
- `resume`先查询同操作status，再prepare；detach先镜像排空后的Gateway完整快照。随后按profile→runtime.owner_transition包住Gateway导入、中央绑定事务；上下文成功后才commit/finish长期所有权。
- `record.input.operation_id`、`original_binding`、`remote_id`、方向和原身份均已持久；`_save_binding`只允许原绑定或同操作目标，并把绑定及mirrored阶段同事务保存。Node适配应沿用这些事实。
- `CredentialOwnership.associate`的已绑定sync分支直接调用中央runtime.sync_credentials。`resume`和缺失绑定收口仍直接调用中央runtime.owner_transition。`main._runtime_owner_transition`也被账号修改、解绑和正式删除使用，最终删除会再次进入原停止上下文。
- `AccountRuntime.owner_transition`当前读取本机HOME、检查执行/内核记录，取得原绑定/新目标的`binding:<32hex>`排他lease，确认sender空闲，停止角色，归档原绑定内核记录；显式解绑先写无令牌handoff，中央绑定更新后以take_ownership发布完整材料。
- `main._v3_cli_identity`调用identity_import，结果包含canonical_env、canonical_process、canonical_prompt。现有RemoteCredentialRefresh.read_identity只返回设备/UUID/来源/环境，不能直接替代完整创建导入载荷。identity_import会调用ensure并采样实际CLI容器，Node接入需要相应受控执行范围。

## 可复用基础

- 独立材料/设备读取已走当前Node HOME，完整定位、稳定身份、实际代次及冻结版本均核对；停用状态仅开放受信纯读。
- 绑定设备纯读经RemoteBoundIdentity；原BoundLoginPublish仅接受原登录Scope及冻结授权摘要，属于原重授权提交，不能作为通用交接发布入口。
- `quiesce_node`已经验证实际Node作业、sender、原内核维护和逐执行文件、角色Running/Pid及实际停止。现有NodeQuiesce只允许`gateway-config:<UUID>`来源，绑定交接需要独立严格模型。
- NodeExecution._inspection_row按安装节点、正式账号、环境与assignment_revision核对Node分配标记。NodeRuntimeHost借用只读Gateway快照时保留原配置。
- 原AccountRuntime.ensure会拒绝credential-handoff；ExecutionGrants._check_environment当前只检查迁移fence及账号/绑定/环境代次。交接期间对新证明和旧证明输入的持久阻断需要同步考虑。

## 接续顺序

1. 在同任务design/implement确认具体交接工作、原操作ID/原绑定/目标绑定、真实短期lease和Node持久待办，区分长期所有权与执行许可。
2. 先接Node实际空闲停止及持久交接意图，再接原完整快照发布和Node绑定投影；保持未知字段、userID/HOME/画像、AT-only与独立RT所有者规则。
3. 中央同操作恢复覆盖Gateway已导入、中央绑定已提交、Node发布部分完成及最终回包未知。历史操作不能覆盖后来轮换结果。
4. 原Gateway明确删除的完整缺失证明、retire无需有效RT及正式删除第二次停止分别验证；各入口沿原owner→profile→environment顺序。
5. 先验证真实双SQLite/文件及本机回归，再用随机cluster-test真实Rust/SSH/TLS核对解绑、Node连续刷新、回交原ID、AT-only、原策略与六个落盘边界。

## 当前状态

- NULL新建草稿由529号220项及530真实链路72.721秒完成当前增量验证。
- 远程交接已由549真实Rust/原HTTP/SSH链路、550号121项回归覆盖。555双节点独立迁移与故障隔离通过。进程采样及完整所有权606、部署备份615、最新制品换批613已完成复查。整体任务保持in_progress，继续规范与Git范围收尾。
