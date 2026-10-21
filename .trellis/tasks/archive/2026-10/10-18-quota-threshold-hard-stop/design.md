# 运行中额度阈值强制停止设计

## 入口与范围

仅 v3 的 normal／warmup run；ordinary batch 通过 normal run 进入。继续读取账号现有 5h／7d 阈值及 QuotaGuard 已合并的有效观察，无数据库 migration，不改阈值默认值。capture、交互续聊、独立网关 API 以及旧 runner 保留现有百分比策略。

核心入口为 QuotaGuard.consume／policy_snapshot、Scheduler._execute、Runner.wait_worker 与 AccountRuntime.wait_worker／cleanup。CLI 观察沿原生 statusLine，API 观察沿发送器白名单；普通任务保持 passthrough，不引入 MITM、usage 查询或真实探测。

## 命中与终止

1. 复用 v3 等待当前 Docker exec 的 0.5 秒循环，在运行存活时执行可选的归属检查；由 Scheduler／Runner 提供当前账号、run、attempt 和完整执行 token，不在底层运行时导入 main 模块。
2. 消费本地观察后读取同一身份的最新窗口与阈值。只因有效窗口 used >= limit 的明确 hit 触发；未知、无效、过期及单次恢复许可不构成强制停止理由。禁用阈值不触发。
3. 先核对该 run 仍运行、身份和执行代次匹配；真实认证失败、用户停止或删除优先。已自然完成的 run 不追溯改为阈值停止。
4. 原子保存 stopping／stop_requested_at 与结构化可追溯的阈值原因，再停止本代 driver／CLI 及其子进程。复用 source／token 校验和 TERM → 有界 KILL 清理，停止动作不等待正常最终回复，也不注入收尾或补充输入。
5. 清理确认成功后才落 stopped、ended_at 和实际退出信息，同步批次 item。错误保留命中窗口、used、limit、observed_at；管理端可读，凭据与身份哈希不公开。
6. 清理失败保留错误和禁止下一作业的运行时门禁，不伪造已经完全停止。服务重启看见持久 stopping 意图时必须完成旧代清理后进入 stopped，不能走 quota_wait 续原 run。

该检查复用现有进程等待循环，不新增每个任务的独立后台线程。实现期间依据真实锁序调整回调位置；网络／Docker 清理在数据库锁外执行，回调不能与最终清理互相等待。正式合成验证以观察已被消费后两秒内发起停止为目标，实际退出另受既有 TERM／KILL 截止约束。

## 批次与养号调度

阈值中断的是本轮，永久终态为 stopped，不写 quota_wait run。批次本身仍可额度等待：命中后不继续投放，未执行项保留 pending；窗口恢复按现有持久单次许可让下一 pending item 取得正式更新机会，保持原 next_launch_at 下限，不重抽原题／补充、不自动重试 stopped item。真实额度未知仍保持未知，不将 reset 到期伪造成 0%。

已启用养号沿 handle_run_terminal 安排下一次正常间隔，新轮仍通过阈值启动门禁；本轮 stopped 不增加认证失败次数。原有额度真正耗尽的恢复语义保持；若有效用量同时命中启用阈值，则本轮按用户选择结束。封号／invalid_grant 保持永久认证门禁，不能因阈值逻辑复活。

## 页面与兼容

保留现有 stopped 状态及错误详情，更新账号阈值提示和模态框：命中会强制结束当前普通任务／养号轮次，已生成文件保留，恢复后批次做下一题；额度来自正式响应的被动观察，可能单次跨阈值。不增加开关、数据库列或新状态。

权威契约 database-guidelines.md 中“当前 CLI 完整收尾”需在实施检查后通过 Update-Spec 与本轮同步。旧共同额度、独立 API、续聊／抓包及历史任务不能被新百分比判断误伤。

## 验证与风险

- 合成观察 → 真实 QuotaGuard → 调度器／SQLite → Docker exec／tmux 停止 → API／浏览器，验证命中、文件保留、原因和下一题投放。
- 覆盖阈值等值、跨阈值、7d、关闭、动态降低阈值、旧身份／代次、自然完成竞争、用户停止、认证失败、重复回调、清理失败及重启。
- 额度回报有延迟，一次模型响应可从 58% 跳到 63%；无法承诺上游实际值绝不越界。中断可能留下部分写入文件，因此只承诺保留现有文件，不承诺本轮产物完整。
- 0.5 秒本地观察循环不能撤回上游已计费请求；本轮不增加网络层估算拦截或付费实验，不承诺对封禁概率产生效果。
- 交付沿既有 v3 同批次 control／account 镜像、最终 GitHub Actions 和自然空闲部署，不新增服务器数据备份，不使用受限账号发起真实模型验证。
