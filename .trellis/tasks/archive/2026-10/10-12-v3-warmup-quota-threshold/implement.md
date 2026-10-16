# v3 养号额度阈值实施计划

## 当前阶段与授权边界

- 用户已确认完整 Brief；任务已进入 in_progress，implement 路由来自个人配置，为 inline。
- 按 trellis-task-brief 展示完整最终说明并取得评审确认后，才启动任务、进入 trellis-route(target=implement)。实施前加载 before-dev 和实际实体/DTO/接口定义。
- 保留原有 22 项脏文件与两个旧任务，不覆盖 official-protocol-capture.md 的用户修改。
- 本任务本地实现与合成验证；不操作旧 5674/8080，不迁账号，不调用真实模型，不自动推送/发布/部署。

## 1. 配置与纯规则

- [x] 读取 main、quota_protocol、Recorder、worker、account_runtime、network-context 和现有相关测试的真实定义，加载所改层规范。
- [x] 为 accounts 定义两项 nullable 整数阈值，同步 _SCHEMA、幂等补列、WarmupConfigIn 的严格校验、读取响应及同事务保存；省略保留、null 关闭。
- [x] 定义养号专用纯判定与摘要契约，覆盖边界值、5h/7d 任一命中、不同 reset、未知/过期、缺 reset 和共同门禁优先级。
- [x] 同步 sidecar 额度纯函数副本；确认共享真实窗口状态不因养号阈值被改为 exhausted。

## 2. 持久许可与调度

- [x] 新增 warmup_quota_admissions；定义稳定 policy/window 键，按 identity/source/代次认领一次正式更新机会，重复保存/点击/重启不重置。
- [x] trigger_account 前置检查、实际启动后重读、立即运行/恢复与 _resume_account 共用规则；不绕过共用额度保护，不阻断普通任务/API。
- [x] 复用 quota_wait 保存养号等待原因、真实 reset 和原会话；恢复原 run，不另建养号任务，不占长期 semaphore/租约。
- [x] 完成账号删除/改绑/停用、关闭养号、用户停止与永久认证错误的优先级；过期许可不能授权新身份或新执行。

## 3. 请求与暂停

- [x] 定义执行级养号作用域并同步 v3 context/白名单与旧 sidecar env；非养号与 idle 清除作用域。
- [x] Recorder 在需要额度更新的第一条请求前持久独占标记，匹配策略/窗口/执行来源，拒绝第二条未知请求；异常标记不能放行。
- [x] 追踪已接受真实 OAuth messages 流；命中后阻断后续请求，response/error 结束后再发布暂停信号，统计过滤不能遗漏收尾。
- [x] 有界消费共享额度变化；API 更新引发阈值命中时，仍等待已有 CLI 请求收尾再暂停，独立 API 不中断。
- [x] worker 识别本代养号等待并保存状态、以 43 退出；原 run/session/workspace/执行快照和证据目录完整，成功/暂停/取消/超时竞态不复活旧工作。

## 4. 页面与文档

- [x] 养号弹窗添加各窗口启用控件与 1～100 整数输入，关闭提交 null；错误输入反馈和后端校验一致。
- [x] 账号状态显示已用/剩余、阈值、等待原因、可信恢复机会与未知；页面加载/刷新不查询 usage。
- [x] 静态资源修改同步版本参数；保持嵌入布局与 390px 窄屏，使用合成账号验证保存、重读和独立窗口关闭。
- [x] 按已实施行为更新 README/本任务 roadmap 状态及必要运行说明，不提前把规划写成已交付。

## 5. 聚焦验证与联合构建

- [x] Python 单元/行为回归覆盖 PRD A1～A7：旧库重复升级；缺字段保留与 null 关闭；非法输入无任何写入；多账号隔离；排队期间变更；未知仅一次；失败/重启/重复触发；同 run 恢复；停止/永久门禁优先。
- [x] Recorder 回归验证真实 OAuth 归属、阈值只作用于养号、已接受流排空、并行流与流错误、第一请求的持久标记、旧 source 拒绝和非养号上下文撤销。
- [x] worker 回归验证暂停不判成功、持久主会话/工作目录、退出 43，以及旧作业信号不影响新代。
- [x] 同步脚本、Python/shell/JS 语法与 diff 空白检查通过；既有额度纯函数两副本字节相同。
- [x] 冻结同一批最终源码，构建 control/account 两镜像；使用隔离 Docker、合成 CLI、临时账户/凭据、本地受控 HTTPS/SSE 验证实际请求数量、当前流完成、下一请求拒绝、共享 API 连续流及重启不重复放行。
- [x] 在同一原 run 第二代中验证 HOME/cwd/--resume 参数和证据保留；不能据此宣称真实官方 CLI 会话已验收。
- [x] 浏览器覆盖桌面/390px、两窗口独立开关、非法值、保存重读、等待原因及旧布局回归。

聚焦命令以实际新增文件为准，现有基线：

```bash
/tmp/v3-verify-venv/bin/python -m unittest discover -s orchestrator -p 'test_*.py'
/tmp/v3-verify-venv/bin/python -m unittest discover -s images/sidecar -p 'test_*.py'
python3 -m py_compile orchestrator/main.py orchestrator/quota_protocol.py orchestrator/account_runtime.py images/sidecar/recorder.py images/account/network-context.py
bash -n images/worker/entrypoint.sh
node --check webui/app.js
git diff --check
```

联合脚本使用 `scripts/v3-stack build --release <新的本地唯一批次> --manifest <新的清单>`。实施时先读取 run_local_verification.py/verify_stack.py 的真实参数，再调用本地验证，不复制旧批次或臆测命令。

## 6. 收尾与回滚点

- [x] 定向检查通过后由 trellis-route(target=check) 进入完整 Check-All，核对配置→请求→DB→调度→Recorder→worker→恢复→UI 的完整链路与默认兼容。
- [x] 保存真实日志和未执行项；失败证据保留，重试仅因修复/明确失败原因进行；新实现按实际影响决定是否需要原 Rust 回归，不因 Python 页面功能例行修改上游协议。
- [ ] 经质量检查后走 Update-Spec，区分本轮新增契约与既有用户修改，再准备精确 Git 范围供 Push 评审。
- [x] 两默认阈值关闭可恢复既有行为；代码/镜像回滚前关闭新阈值并收口等待工作，保留数据库/HOME/会话/证据，不删除数据或触碰旧部署。

真实 OAuth、官方 CLI、公网请求、性能压力、GHCR 发布与美国服务器部署不在本轮本地验收证据中；需要实际执行时单独呈现具体结果和操作范围。

## 首轮本地验证证据（2026-10-13，B 批次）

- 后端 151 项、Recorder 20 项通过；日志 /tmp/v3-warmup-python-b-tests.log、/tmp/v3-warmup-recorder-b-tests.log。
- 两镜像联合批次 local-warmup-20261013-b；冻结源码 SHA256 为 06ab7708c1f0f1bca4a08b79cda81f6c3c524baf89cf0bfc8a41c2a0270e3cfe，已对当前源码重算并匹配。
- /tmp/v3-warmup-https-b-integrity.log：真实镜像 Recorder 与本地受信任 HTTPS/SSE，完整正文 SHA256/长度一致、后续请求拒绝、未知一次、重启不重复、普通作用域放行。
- /tmp/v3-warmup-docker-b.log：固定容器/HOME、同 run 第二代、CLI 测试替身、共享 API 长流、取消/重启/故障、双账号隔离与清理通过。
- /tmp/v3-warmup-stack-browser-b-theme-recheck.log：统一 Compose、HTTP/SSE/WS、实际登录/退出、表单保存重读/独立关闭/非法输入、桌面与 390px、真实主题切换、滚动可达保存按钮、旧哨兵数据与容器不变。补充等待原因断言的最终结果另记 progress.md。
- Python/shell/JS 语法、纯规则副本一致性及 git diff --check 通过；原 22 项脏文件 SHA256 保持。
- worker 暂停控制读取使用实际 shell 函数验证；收尾标记、退出 43 与成功优先级静态追踪至既有 worker 分支；完整官方 CLI 行为未执行。上述证据来自分层行为/组件/Docker 验证，不宣称真实上游端到端已验收。
- 首轮完整检查未通过：CHK-001 可在配置保存和额度消费交错时发布旧窗口；/tmp/v3-warmup-check-publish-race.log 记录 SQLite 50%、共享文件 20%、Recorder 重新判定未命中 30% 阈值。该问题后续已修复，原失败证据保留。

## 最终候选与重检

- C 批次 local-warmup-20261013-c 构建与源码重算一致；清单 /tmp/v3-warmup-c.json，源码 SHA256 e387dababba331d11a9a7f3c89ae3b6777cce4cad680da56f824b4f64203daac。
- CHK-001 发布锁与同份窗口快照已修复，两项新增回归和全部 153 个后端测试通过；未变化的 20 个 Recorder 测试证据复用。
- C 批次 HTTPS/SSE、固定 Docker、统一后台浏览器验证均通过；最终日志 /tmp/v3-warmup-https-c-baseline-recheck.log、/tmp/v3-warmup-docker-c.log、/tmp/v3-warmup-stack-browser-c.log。
- requested=auto、effective=full、confidence=high 的重检通过，剩余 CHK/FBK 为 0。Update-Spec 与提交/发布/部署仍未执行。
