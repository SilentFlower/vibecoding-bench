# Pi 中断自动恢复实施计划

## 开工门禁

- [x] PRD 已按最终结构收敛，无未决产品问题。
- [x] design.md 与本计划覆盖 R1～R6，完整 Brief 已展示，用户以“确认”批准首次实施。
- [x] 经 `trellis-route(target=implement)` 解析为内联执行，未派发子代理。
- [x] 按 `trellis-before-dev` 加载任务与涉及层规范，保留创建任务时已有的未提交变更。

## 实施顺序

1. **复现并固定恢复边界（R1/R2/R3）。**
   - 扩展 `images/pi-agent/recovery-policy.test.mjs`，覆盖缺少结束标记、未知成功 HTTP 响应、硬错误及取消负例。
   - 在 `host.test.mjs` 使用真实 SDK 与回环 SSE，覆盖中途结束、半截工具、重试成功、持续失败交接冷却、摘要共用恢复与不重放工具。
   - 修改 `host.mjs` 的现有分类与结构化故障说明，复用现有有界恢复循环。
2. **接续控制进程与持久调度（R2/R3/R4）。**
   - 修改 `orchestrator/projects_pi.py`，区分正常停止、超时、已就绪进程意外退出和坏协议。
   - 更新 `orchestrator/projects.py` 的事件白名单、收口后的恢复决策、原因保存和显式重试预检。
   - 复用原 60/120/300 秒及低频计划，检查服务端等待、额度、时段、停止和代次竞争。
3. **旧通用错误的受控恢复（R4/R6）。**
   - 在现有 Pi／项目服务边界增加有界会话证据核对及绑定原事件的诊断；不另加任意解除阻塞接口。
   - 将诊断、旧工作恢复资格和计划发布做成幂等且可核对的事务转换。
   - 覆盖两空间、关闭计划、事件覆盖、并发启动、坏会话、证据时间不符、未知输入及门禁失败。
   - 已确认修复 FBK-001：隔离旧资产读取失败，验证其他账号继续恢复及新故障提示不被覆盖。
4. **页面说明（R5）。**
   - 派生恢复摘要并在 `webui/projects.js` 复用既有计划倒计时、SSE 和事件说明。
   - 显示具体原因、尝试次数和下次时间，保留账号／空间切换的旧响应丢弃规则。
   - 同步 `webui/index.html` 的受影响资源版本；不新增后台轮询。
5. **检查、规范与交付（全部验收）。**
   - 执行下方必要验证，记录成功命令和实际限制。
   - 通过 `trellis-route(target=check)` 进入 Check-All；修复本次引入的问题。
   - 按 `trellis-update-spec` 更新模型恢复及旧诊断契约，刷新 `images/pi-agent/README.md`。
   - 按既有 Push／发布 SOP 展示精确变更和发布范围。上线时核对 10-23 仍指向原 work，受控恢复后记录真实状态；未执行上线时明确当前仅完成代码交付。

## 验证命令与场景

### 本地自动化

- `cd images/pi-agent && node --test recovery-policy.test.mjs`：分类的正负例。
- `cd images/pi-agent && npm test`：真实 SDK 与回环上游；在最终代码稳定后完整运行一次。
- `PYTHONPATH=orchestrator .venv/bin/python -m unittest test_projects_agent test_projects_schedule test_projects_schedule_edges test_projects_runtime_resilience test_projects_pi_round test_projects_cycles`：共享控制端、计划持久化、恢复与两空间隔离。新增的必要聚焦用例一并运行。
- `node --check webui/projects.js`：前端语法。
- 若改动镜像包含范围，检查 `images/v3/` 的 Pi COPY 与 `deploy/v3/manage.py` 源码冻结名单同步，并运行对应部署管理单测。

### 行为验收

- 回环 SSE 的首次响应缺少结束标记，随后返回成功：同一目标恢复，半截工具不执行，既有工具回执不重放。
- 持续断流：快速恢复耗尽后保留可见的低频下一次执行，重启不归零计数，也不提前执行。
- Pi ready 后退出且原执行可确认收口：原目标恢复；坏协议或未确认终端输入仍显示具体阻塞。
- 合成旧通用错误与原会话匹配：诊断幂等、自动计划原样保留、显式恢复可用；错误事件／会话不符时不解除阻塞。
- 本地浏览器使用合成 API/SSE 状态检查故障说明、尝试次数、倒计时及账号／空间切换；不发送真实上游模型请求。
- 10-23 正式恢复核验与本地合成验收分开记录：原 work/session、通过进度、终端投递审计和最新计划状态必须可核对。

## 回滚点

- 模型分类改动可独立回退，但必须同时兼容已发布的结构化故障事件。
- 控制端状态转换与旧诊断以负例回归为开关条件，不以批量状态重置兜底。
- 生产发布前按既有 SOP 保留恢复点；回滚不删除凭据、工作区、会话或投递记录。

## 当前验证记录

- 用户已选择“修复全部”，FBK-001 已补齐资产读取异常隔离和并发提示保护；定向回归先复现四种失败组合，再验证修复后原目标保留、另一个账号恢复正常。
- SDK：`cd images/pi-agent && npm test`，62 项全部通过；修复 FBK-001 未修改 SDK 或其测试，重检复用该有效结果。
- Python：`.venv/bin/python -m unittest discover -s orchestrator -p 'test_projects*.py'`，最终 363 项全部通过，日志为 `.deploy/pi-interruption-auto-recovery/python-tests-repair.log`。
- 浏览器：`.venv/bin/python deploy/v3/verify_pi_projects_browser.py --evidence .deploy/pi-interruption-auto-recovery/browser-repair`，55 项检查通过，报告内源码摘要与当前代码一致；覆盖实际 Chrome、回环 API、SQLite 和 SSE，未调用真实上游模型。
- `node --check images/pi-agent/host.mjs`、`node --check webui/projects.js`、Python 编译及 `git diff --check` 均通过。
- Check-All：复用前轮完整追踪，针对 FBK-001 完成闭合重检；当前 CHK=0、FBK=0，无风险接受项。
- [上线后验证] 新版尚未发布；10-23 的原工作仍为 `79ce7f8e88e941bea99e418c26dcaca8`。已只读核对原会话目录匹配，发布后仍需核对同一工作自动续接，不将本地合成验证描述为线上已恢复。
