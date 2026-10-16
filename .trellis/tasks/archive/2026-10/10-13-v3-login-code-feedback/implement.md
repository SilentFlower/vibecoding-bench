# v3 授权码输入反馈与登录恢复 — 实施计划

## 1. 开始条件

- [x] 最新 PRD、设计、实施计划收敛，无阻塞产品问题；刷新并完整展示 Brief，得到本任务评审确认后才 `task.py start`。
- [x] 通过 `trellis-route(target=implement)` 进入实现；先加载 `trellis-before-dev` 与任务清单中的相关规范。
- [x] 再读 `LoginSession`、`LoginManager`、`AccountRuntime`、草稿操作模型和页面登录状态定义，确认真实字段和方法；不把拟新增契约误当现有 API。
- [x] 固定 baseline：纳入三项焦点/提示/键盘验证改动；保留其余 22 项无关改动与子仓 HEAD。

## 2. 按序实施

- [x] I1（R1、R2、R6）：实现运行时 stdin → 原 tmux 的有界投递、执行证明/存活校验、秘密不进 argv、临时 buffer 清理；先在隔离 Docker 验证 EOF 和 literal paste。
- [x] I2（R2、R5、R6）：新增安全 POST/GET 回执接口和会话回执集合，同标识幂等、结果未知保护、输入限额与无泄漏错误体；与提交/取消共用锁保护。
- [x] I3（R1、R2、R5）：增加独立输入框和发送状态、原生粘贴、Enter、防连点及窗口生命周期清理；v3 授权终端只读输出，旧版/续聊保留输入；同步静态版本与明暗布局。
- [x] I4（R3、R5）：新增草稿安全恢复入口和 `can_reconcile`；修复未绑定旧会话及名称占用收口，保护新代次/坏归属/未知提交，不删除 HOME。
- [x] I5（R4、R6）：生成脱敏代理摘要，区分未知/未配置，调整草稿列与动作入口；不改变正式账号选择。
- [x] I6（A1–A6）：更新已有单测和隔离验证脚本，涵盖真实输入链、未知回包、恢复保护及正式路径回归。

## 3. 验证计划

### 基础与行为回归

```bash
node --check webui/app.js
python3 -m py_compile orchestrator/main.py orchestrator/account_runtime.py orchestrator/login_drafts.py
PYTHONPATH=orchestrator python3 -m unittest orchestrator.test_login_reauth orchestrator.test_login_drafts orchestrator.test_account_runtime
git diff --check
```

测试环境需安装 `orchestrator/requirements.txt` 和 `orchestrator/requirements-test.txt`。本轮实际使用 `/tmp/v3-verify-venv/bin/python`，在 `orchestrator/` 下执行 `-m unittest test_login_reauth test_login_drafts test_account_runtime`。重点验证真实临时 SQLite/私有文件保护，不只断言实现细节；HTTP 客户端仅用于 ASGI 回归，不新增产品运行依赖。

### 隔离 Docker 与浏览器

- 使用现有联合构建清单，在随机部署/独立目录运行既有入口：

```text
python3 deploy/v3/run_local_verification.py --manifest <最终联合清单>
python3 deploy/v3/verify_stack.py --manifest <同一清单> --browser --reauth
```

- `verify_reauth_stack.py` 改用真实浏览器输入框/按钮和 HTTP 投递；不直接用 `ws.send` 替代用户输入，断线后独立提交与同 SID 输出重连分开验证。
- Ctrl+V 与右键粘贴验证实际原生插入和 input 事件；平台剪贴板权限/无右键驱动支持时记录具体未执行项，不能用 JS 赋值冒充真实粘贴。
- 增加重复 request_id、回包丢失、半途失败、非法/超长输入、结束/换代及监听清理场景；断言单次注入、正确状态、秘密未进入错误/日志/argv。
- `verify_login_drafts.py` 覆盖清理故障与停机执行证明，恢复后旧 SID/名称释放但 HOME/身份不变；冲突归属/提交/忙碌拒绝；代理脱敏展示。
- 另用 2.1.293 真实 native 二进制、全新 HOME 和 `network_mode=none` 验证隐藏输入仍进入 CLI 校验。测试二进制不进仓库、正式镜像或联合包；不向真实 OAuth 请求发测试码。

## 4. 检查、交付与回滚点

- [x] 完成对应检查后通过 `trellis-route(target=check)` 进入 Check-All；共享契约/跨层输入与恢复保护按适用深度检查，记录合成与真实实验边界。
- [x] 使用 `trellis-update-spec` 更新输入提交、回执幂等、草稿对账与代理摘要契约；重复故障分析补充已证实事实，底层未知原因不写成定论。
- [x] 按工作流展示精确提交范围；只提交本任务产品文件、规范和任务记录，保留无关 baseline。
- [ ] 最终构建/Actions/GHCR/部署按 v3 SOP 和当前用户授权处理，核对发布清单、活动登录和旧服务基线；不能把已有生产热补丁当永久镜像交付。
- [ ] 回滚点：新 HTTP 投递与只读窗口一起回退，避免只退一层；对账入口撤销后保留已有私有元数据/环境。无需数据库数据回滚，不处理真实账号历史。
