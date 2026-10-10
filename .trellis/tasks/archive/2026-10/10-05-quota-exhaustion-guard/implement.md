# 实施计划

## 启动条件

- [x] 三件套已收敛，完整 Brief 已展示，用户确认评审后才执行 `task.py start`。
- [x] 经 `trellis-route(target=implement)` 进入实现；默认不自行派子 agent，执行方式服从用户与项目规则。
- [x] 读取 `trellis-before-dev` 及受影响层规范，检查对应 DTO/类定义；不将本文拟新增字段误当成现有 API。
- [x] 保护初始工作区改动：`.trellis/spec/vibecoding-bench/deploy/official-protocol-capture.md` 和 `cc2api` 子模块；不得覆盖或回退。

## 有序实施

1. 被动额度协议与持久化
   - [x] 在 quota_protocol.py 添加纯窗口解析、拒绝分类、部分合并、跨周期和最晚恢复时间判定；同步 sidecar 构建副本。
   - [x] 新增账号额度表、观察游标表及必要 run 列，幂等升级并保持旧数据。
   - [x] 定义观察、共享门禁、执行信号的最小 JSON 契约；身份/来源/generation 校验及本地 AT 哈希归属不含敏感明文。
   - [x] 单测先验证未知、单窗口、双窗口、非法/缺失数据、跨周期、拒绝优先和乱序处理。
2. sidecar 与 worker 运行内保护
   - [x] `images/sidecar/recorder.py` 增加响应头观察和请求门禁，原统计/完整抓包行为保持兼容；本地拦截不产生上游请求。
   - [x] `Runner.start_run()` 和 `Runner.start_continue()` 增加只读账号状态目录及执行控制挂载；普通 continue 也产生持久化观察。
   - [x] worker 在任何恢复/收尾提示之前处理额度信号；保存状态后停止重试，合成 API 错误必须在 success 前识别。
   - [x] 明确额度退出结果及状态文件契约，修复 10-2 的 rate_limit/account_on_hold 合成消息；认证和 API 超时分类不回归。
3. 全部入口的等待与自动恢复
   - [x] 普通/再次运行/抓包共享启动前最终检查；额度状态不再仅展示。
   - [x] 增加 quota_wait 状态、执行记录归档、同 run/session 恢复和一次正常恢复认领；模型/CLI/effort/权限/prompt/timeout 配置保持快照。
   - [x] 批次停止投新题，等待不计完成，恢复先原 run 后后续题；检查所有状态 SQL、人工 pause/resume 与 done_count。
   - [x] 养号认领和终态支持独立额度等待，不选新题、不重复建任务、不累计 auth_failures；关闭后不恢复。
   - [x] stop/delete/账号停用/绑定切换覆盖等待状态，防止旧回调或自动认领复活已停止工作。
4. 继续对话及启动恢复
   - [x] ContinueSession 增加等待/代次信息，启动可先登记等待会话；HTTP 路由不阻塞等待。
   - [x] WS 后端拒绝等待期输入，停止旧 exec；到期自动恢复 PTY，关闭/断连取消，不重放输入。
   - [x] 额度后台挂入 lifespan，消费偏移持久化，收口前强制消费；与旧养号 stale recovery 协调。
   - [x] 验证观察/DB 更新/容器清理/queued 认领之间崩溃可恢复，旧容器不与恢复执行重叠。
5. 页面与规格
   - [x] 更新 `webui/app.js`、必要的 `index.html`/`style.css`，显示被动来源、观察时间、未知/过期、quota_wait 与恢复时间；停止按钮覆盖等待状态。
   - [x] continue 状态事件同步输入禁用/恢复，关闭 modal 后不重连；手动 quota 按钮仍只由显式点击触发。
   - [x] 确认暗色、亮色、窄屏布局和输出 escapeHTML，SSE 不触发主动额度查询。
   - [x] 在任务设计及验证记录中记录被动额度与状态契约、三镜像配套交付和回滚限制；正式 Spec Update 留待检查后，保留初始脏 spec。

## 验证命令与场景

实现完成后按以下层次执行，不在当前规划阶段运行产品测试或真实模型请求。

```bash
python3 -m py_compile orchestrator/main.py images/sidecar/recorder.py
bash -n images/worker/entrypoint.sh
node --check webui/app.js
python3 -m unittest discover -s orchestrator -p 'test_*.py'
python3 -m unittest discover -s images/sidecar -p 'test_*.py'
git diff --check
```

测试沿用 unittest、临时 SQLite、现有 Docker mock；sidecar 测试用轻量 mitmproxy flow mock，不要求额外真实代理或上游认证。worker 的内嵌 Python 判定与退出行为通过脱敏 JSONL/控制文件夹具执行，不能只用字符串包含断言验证业务逻辑。

| 对应验收 | 验证证据 |
| --- | --- |
| AC1、AC2 | 六类入口及排队后变化都拦截；被拦时没有正式 worker/上游模型请求 |
| AC3、AC4 | 10-2 合成错误不成功、不跳题；正常 assistant、认证、超时仍正确 |
| AC5、AC6 | 多次 tick 不重复投放；两个窗口取最晚，自动恢复保留题目/身份；暂停与关闭优先 |
| AC7、AC10 | 无首次记录可正常运行，缺头保留；未知 reset 等待；允许/拒绝与跨周期正确 |
| AC8 | 恢复所有关键崩溃点，额度等待跨重启保存且旧容器清理完成；其它账号继续 |
| AC9 | 自动路径 mock 主动接口为“调用即失败”，确认无额外 usage/探测/查询 worker；日志无敏感明文 |
| AC11 | continue 启动/输入/运行中门禁，文本和二进制输入均覆盖；到期自动恢复，无输入重放/关闭复活；抓包限频和快照不回归 |

本地整体场景使用模拟上游响应和现有容器/PTY mock；不得消耗生产额度来验证拒绝。镜像 smoke 使用现有镜像加载只读挂载的当前源码并禁用网络，不自动发布或部署。

## 评审与回滚点

- [x] 解析/存储、运行内阻断、调度恢复、continue 四阶段各用对应行为测试证明，再进入下一层。
- [x] 完成后进入 `trellis-route(target=check)` 所有的 Check-All，核对 PRD AC1–AC11、SQL 活跃状态、跨层 JSON 字段和三镜像依赖。
- [x] 验证通过后按 workflow 更新规格、展示变更，提交/推送与生产发布分别遵守对应门禁。
- [ ] 回滚只新增表/列的实现时保留数据，先停止等待工作；旧版本不会识别 quota_wait，不能直接当正常 active 恢复。
