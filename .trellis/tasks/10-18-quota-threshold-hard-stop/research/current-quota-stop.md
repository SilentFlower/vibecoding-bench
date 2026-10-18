# 当前额度与停止机制

## 已核实的入口

- orchestrator/main.py:2848 policy_snapshot：普通任务／养号读取相同 warmup_quota_5h_limit_percent、warmup_quota_7d_limit_percent 字段，不因字段历史命名而只对养号生效。
- orchestrator/main.py:2928 _policy_decision：v3 按真实窗口、阈值与持久 admission 判断启动；旧命中窗口到期后允许一个已有正常执行更新额度，不将旧缓存改为 0%。
- orchestrator/main.py:3024 _admit_warmup、:3077 admit：正常 run 启动前最终门禁及同周期恢复许可；HTTP／Docker 操作不得放进 SQLite 锁。
- orchestrator/main.py:3240 consume：消费已登记 CLI／API 白名单观察并发布当前账号状态，不主动查询 usage；CLI 观察只能证明额度，不提供永久认证状态。
- orchestrator/main.py:6523 _execute：最终执行前再次读取账号与 run 代次，通过 admit 后启动；退出路径按 43／quota_wait、42／auth_failed 和其它终态分类，finally 收口并释放。
- orchestrator/main.py:6781 _mark_quota_wait：保留原 run／task／批次和恢复配置；需沿真实定义核对新增中断入口，避免先写终态再调用仅接受 queued／running 的 CAS 更新造成丢失。

## v3 执行及停止

- orchestrator/account_runtime.py:1202：普通 run 的网络模式为 passthrough，使用原生 CLI statusLine 被动采集；:1228 将 QUOTA_WARMUP 设为 0。不能为了阈值改回普通任务 MITM 或新增后台 usage 请求。
- orchestrator/account_runtime.py:1345 wait_worker：等待当前 Docker exec 并每 0.5 秒核对。需研究在此入口或已有调度观察循环增加当前 source 的阈值检查，以最小化跨入口重复状态机。
- orchestrator/account_runtime.py:1373 cleanup：仅接受匹配本代 token，environment 锁内核对当前 job；TERM 进程组，最多 10 秒后 KILL，再调用 v3-cli-control 清理 UID1000 子进程；保留固定容器、独立 API、HOME 和项目。清理未知状态失败则隔离并拒绝后续作业。
- images/worker/entrypoint.sh:1013 check_quota_pause：读取本代来源对应控制信号，可保存额度暂停状态。现有 QUOTA_WARMUP 仅用于养号收尾协议，直接重用前必须核对普通任务的停止与最终快照顺序。
- images/sidecar/recorder.py:419 running／_watch_warmup：养号通过当前已接受流的完整收尾后发布暂停；用户新要求需要避免把这种继续收尾当作强制中断。

## 现有验证位置

- orchestrator/test_warmup_quota.py：阈值等值、关闭、缺 reset、窗口到期、持久许可、配置发布竞争和普通入口。
- orchestrator/test_quota.py、orchestrator/test_cli_quota.py：共同额度、观察验证和自动路径禁止主动请求。
- orchestrator/test_account_runtime.py：执行代次隔离、cleanup 不停止独立 API、共享作业和重启清理。
- deploy/v3/verify_warmup_quota.py：合成 HTTPS 上游与真实代理的旧养号收尾协议。新验收须补充真实 busy driver 的强制中断，不只改单位测试。

## 已确认产品行为

用户回复“2”，选择永久结束本轮。原 run／item 使用 stopped，禁止额度恢复和服务重启自动续跑；批次等待额度与原投放间隔后继续下一 pending item，定时养号按现有调度安排新一轮。

## 补充核对

- orchestrator/main.py:6170 submit_batch／_execute_batch：投放仅选择 pending／paused item；现有 stopped 不会在自动恢复时被选中。显式人工重新启动批次有独立语义，本轮不将其当自动恢复。
- orchestrator/main.py:3667：无活动 run 的 quota_wait 批次可在普通额度策略放行后恢复；需要保护原 next_launch_at，避免强制停止顺带抹掉投放间隔。
- orchestrator/main.py:6844：_update_batch_item_for_run 支持 stopped；现有终态集合包含 stopped，不必扩展数据库状态。
- orchestrator/main.py:7062 handle_run_terminal：已结束养号按现有随机间隔安排新轮；不能将阈值停止误计成认证失败。
- webui/app.js:515 阈值提示及 webui/index.html:426 模态框说明仍描述暂停后续／完整收尾，后者还残留自动查询额度表述；必须随本次行为一起同步，避免用户继续误解。
