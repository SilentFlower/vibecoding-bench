# 实施计划

## 前置

- [x] 取证三类 UI/生命周期问题并读取已有模型、接口、状态、删除和固定环境规范。
- [x] 用户决定：全部清理未提交草稿的专属容器和目录，保护正式账号与历史。
- [x] 核对实际 restart 策略及官方 CLI 2.1.293 新授权入口；记录来源而不保存授权秘密。
- [x] 三件套与完整 Brief 已展示并获“确认”；任务已启动，implement 使用个人默认 inline。

## 顺序

1. 先写有区分度的回归用例：新/旧官方入口、终态提示覆盖、未提交环境不可见、删除/提交/重登冲突及重启恢复。
2. 实现草稿持久元数据及 v3 列表/继续/重登/删除接口；使用既有 owner/profile/environment 锁和资源证明，保留不确定失败。
3. 账号页展示草稿状态与受控操作，不混入正式账号下拉；接入删除确认与失败后可见重试。
4. 修复 URL 精确入口、完整提取、终端状态与重新登录入口；保留同 sid 重连、无输入重放及绑定重授权契约。
5. 运行定向 Python 回归、相关既有账号/运行/重授权回归及语法检查，再在新联合镜像的隔离 Docker/Chrome 验证。
6. 返回 Phase 2.1 Pre-Check → trellis-route(target=check) / Check-All；修复复查后按后续指令更新规范并准备精确提交。

## 验证命令

- /tmp/v3-verify-venv/bin/python -m unittest discover -s orchestrator -p 'test_*.py'
- /tmp/v3-verify-venv/bin/python -m unittest discover -s deploy/v3 -p 'test_*.py'
- node --check webui/app.js；py_compile 受影响 Python；git diff --check。
- 使用受版本控制的 deploy/v3/manage.py 联合 build；隔离 verify_stack.py --browser --reauth 扩展草稿场景，随机部署和内部 mock 上游，不访问真实 OAuth。

## 场景—路径—期望

| 场景 | 路径 | 期望 |
|---|---|---|
| 新建未登录 | Chrome → start → 固定环境/草稿 → 账号列表 | 准备/登录状态可见，无正式账号 ID，无任务/养号可用资格 |
| CLI 完整链接 | 真 tmux 输出脱敏支持形状 → status → textarea | 新旧入口与换行完整；恶意/截断拒绝，HTTP 复制可用 |
| 连接断开 | Chrome → 新票据 → 原 sid/tmux | 重连原会话，无离线输入重放 |
| 会话结束与输入 | CLI/tmux 退出 → status → UI 输入/按钮 | 结束原因不被覆盖，提供明确重新登录；有效产物可按认证检查提交 |
| 刷新及双页继续 | UI 重载 → 草稿查询/继续 | 找到原草稿，活跃原 SID 不重启，不产生第二容器 |
| 服务重启 | 遗留执行/草稿 → 新管理进程 reconcile → UI | 可见中断状态，HOME/身份保留，不伪造原交互会话，不全部自启 |
| 完整删除 | UI 明确确认 → 取消/停止/移除 → DB/目录 | 只清本草稿容器、目录与记录，列表消失，同名可重新创建 |
| 删除部分失败 | Docker/文件故障 → deleting/reconcile → 重试 | 不假成功，记录可见，重复清理幂等且不丢未知提交 |
| 竞态与换代 | 删除/提交/重登并发、旧页面请求 | 不误删已提交账号或新代草稿；冲突明确拒绝 |
| 保护边界 | 正式/软删除账号、历史、符号链接、错部署容器 | 新接口拒绝越界，无凭据/历史变化 |
| 原有功能 | 关联重授权/回执恢复/API与CLI普通并行 | 既有凭据刷新所有权、门禁、身份与历史保持 |

## 风险与回滚

- 重点文件：orchestrator/main.py、account_runtime.py、login_terminal.py、webui/{app.js,index.html,style.css}、相关测试/隔离验证。
- 先把清理证明与失败恢复建立，再开放完整删除按钮；不进行宽标签/前缀批量清理，不碰旧部署。
- 真实 10-13 登录仍由用户操作；开发只用合成草稿，不通过热补丁或重启生产管理器验证新生命周期。

## 实现及验证记录

- 新增 LoginDraftStore 私有标记和四个草稿 API；账号页独立展示，不向 state.accounts 混入草稿。首次保存的中间账号保持禁用，提交标记仍存在时正式列表及可用账号查询继续隔离。
- 活跃继续复用 SID；显式重登新 SID/新草稿代次，仍使用同环境、HOME 身份、代理和 CLI 缓存。遗留草稿可发现；重启后的产物经真实 CLI auth status 检查才能进入待提交。
- 删除使用 owner → profile → environment，验证正式/历史/未知提交、精确 labels、目录归属和发送器空闲。deleting 位于环境外，Docker 或最终标记清理失败保留可见重试。
- 官方入口按精确主机/路径组合识别，先拼完整有界 query 再验证，防止换行的重复参数被提前接受。终端结束与普通断线分开，离线输入不会覆盖终态；页面有明确重新登录入口。
- 单测与隔离 Chrome/Docker 多轮发现并修正状态回调变量、刷新测试误点旧文档、正常停机与突然退出混淆、测试基线清理遗漏。保留各轮日志，最终证据以最新联合镜像为准。
- Check-All 首轮 CHK-001、FBK-001/002/003 已修复：旧部署凭据就绪兼容、重登锁内 404、迟到 WS 异常终态保护、单条损坏元数据可见且禁用操作。定向 41 项及最终 188 项 orchestrator 回归通过；29 项部署回归通过。
- 最终联合镜像批次 local-drafts-20261013-k 的隔离 verify_stack.py --browser --reauth 退出 0，覆盖真实 Chrome/HTTP/WS/tmux、管理器 SIGKILL 后恢复、原环境提交和完整草稿删除；CLI/OAuth 使用合成替身，不访问真实授权上游。
- 最终冻结源码 SHA256 为 b664a600c8e54a581121a3172c71a3833c35907ac97a1848f044873c57b4ed1d，与清单一致；语法与 diff 检查通过，22 项保留变更内容未变。重检无剩余 CHK/FBK；真实 OAuth/正式 API 保留为上线后验证。
- 现阶段未提交 Git、未发布 GHCR、未改生产服务。Check-All 通过后仍按 Phase 3 的规范更新及精确交付门禁推进。

## 交付记录

- 生命周期、完整清理、官方 URL 和终态契约已同步到 backend/account-runtime-v3.md 与 frontend/hook-guidelines.md，两个索引同步；规范链接、实际签名及 diff 检查通过。
- 精确暂存检查发现两个新增 Python 文件末尾空行，已仅移除这两行；AST 与已验证版本一致，git diff --cached --check 覆盖全部 17 个业务/规范文件后通过。上述 k 镜像冻结证据对应空行修正前输入；发布镜像须从交付提交重新构建。
- 业务变更已按确认范围提交并推送到 v3；当前步骤同步任务记录与完成状态。真实 OAuth/正式 API 仍待后续部署验收，未发布 GHCR 或操作生产服务。
