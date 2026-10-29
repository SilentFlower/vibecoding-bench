# 联合实施计划

## 顺序与责任

1. 完成本父任务及两个子任务的规划收敛、Brief 展示与用户评审；评审批准覆盖下述两项既定范围后，先激活观察效率子任务，后激活验收子任务。
2. 子任务 `10-26-pi-observation-efficiency`：先核实固定 CLI 钩子并实现作业级唤醒提示、原生交互与稳定画面回归，再实现 Python 等待和模型视图及 SDK/上下文基线回归，保存模型请求和载荷的回放对比。
3. 子任务 `10-26-attrs-verification-contract-feedback`：封存旧观察器摘要，修未来业务观察器，接入旧冻结适配与白名单反馈，用真实候选和反例验证。
4. 父任务在两个子任务代码及定向验证完成后执行统一联合 Check-All，两个子任务的收尾合并到本次联合交付，检查双空间、原输入事实、页面快照和通过证明没有变化，更新相关规范。

## 检查点

- [x] 两个子任务分别具备最新 PRD、design、implement 和 Brief；用户已确认联合方案及交互事件唤醒增量决定，按顺序实施。
- [x] 观察阶段：噪声等待、钩子/原生事件即时唤醒、无钩子菜单快速检测、取消、旧观察 ID 和原总预算通过。
- [x] 增量阶段：可还原差异、首次/摘要/重启完整基线、按需完整画面、原始页面快照及 mock 上游调用计数通过。
- [x] 验收阶段：原候选的修正业务矩阵及六条公开回归通过，真实错误反例失败，旧冻结来源和反馈白名单通过。
- [x] 两空间与原适配器的有关回归通过，结果保存在任务 research/validation.md，不能把未执行的全套验证写成通过。
- [x] 经 trellis-route(target=check) 进入 Check-All；按检查 owner 完成后续规范与提交交接。本轮没有发布或部署授权。

## 验证入口

观察子任务详细命令见其 implement.md；验收子任务同理。联合验证覆盖 `test_projects_agent`、`test_projects_terminal`、`test_projects_feed`、`test_projects_store`、`test_projects_single_objective`、`test_projects_pi_round`、`test_projects_verification_recovery`、`test_projects_verification_history`，以及 schema/weighted/Arrow/新增 attrs 适配器用例。

Pi 宿主使用现有 `node --test images/pi-agent/host.test.mjs` 管道夹具，不调用真实供应商；若增加独立投影模块则补必要用例并核对 Docker COPY/构建上下文。观察性能回放与真实上游收费明确分开。

## 回退点与现有工作区

任务创建基线的四个修改路径均为现有 Trellis/Flower 变更，本轮不覆盖、不提交其内容。仅本轮业务文件及对应文档/任务记录进入后续交付范围。两个子任务之间保存独立验证证据；发现约定外行为先更新受影响规划，不扩大到生产修复或改写历史。

## 当前交付状态

两个子任务与联合 Check-All 已通过，规范已同步；代码提交、推送及三个任务的 completed/Close 尚待精确 Git 计划确认。确认后先交付共同业务代码，再分别同步两个子任务，最后同步父任务，避免父任务先于子任务收尾。
