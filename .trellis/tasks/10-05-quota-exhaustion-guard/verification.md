# 本地实现验收证据

日期：2026-10-06。验证均在本地临时 SQLite、脱敏凭据及 Docker/PTY 替身中进行；没有访问生产账号、发送真实模型请求或部署服务。

## 实际命令与结果

| 验证 | 命令或方法 | 结果 |
| --- | --- | --- |
| 后端全量回归 | `/tmp/vibebench-quota-venv/bin/python -m unittest discover -s orchestrator -p 'test_*.py'` | 98 项通过；临时 venv 使用原 requirements.txt，没有新增项目依赖 |
| sidecar 回归 | `python3 -m unittest discover -s images/sidecar -p 'test_*.py'` | 9 项通过 |
| Python 语法 | `python3 -m py_compile orchestrator/main.py orchestrator/quota_protocol.py images/sidecar/recorder.py images/sidecar/quota_protocol.py` | 通过 |
| worker 语法 | `bash -n images/worker/entrypoint.sh` | 通过 |
| WebUI 语法 | `node --check webui/app.js` | 通过 |
| 协议副本 | `cmp orchestrator/quota_protocol.py images/sidecar/quota_protocol.py` | 字节一致 |
| 差异格式 | `git diff --check` | 通过 |
| 容器加载 | 现有 orchestrator/sidecar 镜像，源码只读挂载，`--network none` | main 导入及 init_db 成功；mitmproxy 11.1.3 的 load_script 加载 Recorder 成功 |
| 浏览器交互 | Chrome CDP + 真实 WebUI/API/WS + 临时 SQLite + socketpair PTY | 暗/亮主题、1440/390 宽度、账号/批次/run/续聊等待通过；到期恢复、关闭和输入丢弃通过 |
| 初始已有改动 | 两个已有 dirty path 的 diff SHA256 对比 task.json 初始基线 | 完全一致；cc2api 内部仍干净 |

命令输出在 `/tmp/vibebench-quota-all.log`；浏览器脚本、截图及结果在 `/tmp/vibebench-quota-ui/`。这些是临时验证产物，重启环境可能清除；本文件保留关键断言。

## 验收映射

| 验收 | 实现入口 | 关键行为证据 |
| --- | --- | --- |
| AC1 | Scheduler._execute、WarmupScheduler.trigger_account、ContinueManager.start/send_input；Recorder._quota_gate | 单次、批次、再次运行、养号、抓包、续聊共同拦截；拒绝时不创建 worker，下一条模型请求由 sidecar 本地响应 |
| AC2 | semaphore 后重读账号与额度 | 排队后才发生耗尽仍进入 quota_wait，未调用 start_run |
| AC3 | worker classify_claude_completion、Scheduler 错误提示优先 | 直接执行内嵌 Python：rate_limit 不成功；明确 limit 保留原题等待，普通速率错误 failed；正常 assistant 可完成 |
| AC4 | worker 合成分类、QuotaGuard.record_auth_failure | timeout、认证、invalid_grant、account_on_hold 分类；旧 exit 0 不覆盖错误；封号永久门禁，不参与额度恢复 |
| AC5 | quota_attempt、execution_model、quota_identity、会话基线 | 多次 tick 单次认领；原 run/task/prompt/版本/effort/workspace/session 不变；空模型快照也不会读取新的全局覆盖 |
| AC6 | quota_decision、QuotaGuard._resume_account | 两窗口取最晚 reset；到期先认领一个原任务，真实允许响应后放行其它等待；再拒绝重新等待；暂停/停止/关闭/停用优先 |
| AC7 | quota_observation/merge_quota_observation、record_worker_limit、页面额度摘要 | 未知允许正常首次任务；缺头与非法值不清证据；无可信 reset 等待；页面区分未知、已到期和手动更新 |
| AC8 | 游标、QuotaGuard.recover/_recover_control、严格容器清理 | 半行、轮换、重启、认领后崩溃、控制先到而日志失败均覆盖；清理失败不启用恢复；其它账号正常运行 |
| AC9 | 所有自动路径 mock 查询为调用即失败；请求归属及 API 过滤 | 主动 usage/cc2api refresh_usage 为 0；无查询 worker 或模型探测；观察/共享文件/API 不包含 AT/RT 明文，API 不暴露内部身份或哈希 |
| AC10 | 纯协议解析/合并测试 | allowed/rejected 同响应区分；模型专属窗口不阻断通用窗口；跨周期高位、乱序、缓存窗口自身时间与同时间拒绝优先均覆盖 |
| AC11 | ContinueManager、真实 continue WS、capture_resume_ready | 文本及二进制等待输入均丢弃；自动恢复原 session，关闭后不复活；抓包 run 与抓包续聊恢复保持串行、120 秒间隔和至少 15 分钟暂停 |

浏览器结果：等待期发送的两种输入均没有进入 PTY；恢复后 PTY 收到的内容仅为 `新的输入`。正常恢复创建次数为 1，关闭后 session 数为 0，usage 查询、refresh_usage 和 JavaScript 异常均为 0。

## 本地交付边界

完整保护需要配套交付 orchestrator、worker、sidecar 和 WebUI。数据库只新增两表与四个 run 列，旧数据在连续两次升级后保留；历史 quota_attempt=0，其余新字段为 NULL。

上线后由部署执行者按既有 SOP 验证三镜像一致、实际只读挂载、首次正常任务响应头采集和账号页面更新。当前没有构造生产耗尽，没有修改远程数据库或恢复 10-2。被动保护不能提前预测首次耗尽；缺少可信 reset 时会持续等待更多合法证据，也不能据此证明历史封号原因。
