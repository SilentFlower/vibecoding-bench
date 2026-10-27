# 实施与验证计划

## 执行约定

- 当前已获首次 Brief 批准并处于 in_progress；task.py start、trellis-route(target=implement) 和 trellis-before-dev 已执行。
- 默认在当前工作区 inline 执行；没有使用子代理的授权或必要性，不创建 seed-only 的上下文清单来替代实际规范读取。
- 开始前的两份 `trellis-update-spec/SKILL.md` 本地改动属于既有用户工作，不纳入本任务实现或提交范围。

## 实施顺序

1. [x] 共享 Python 兼容策略：严格解析版本、默认 minor 与可选 exact；接入 profile 校验、两份离线环境准备、缓存证明和实际验收环境。先补补丁差异、跨主次、非法版本、探测失败、旧 profile／缓存的回归。
2. [x] 原生回归一致性：更新新控制器，并按已核 SHA 和唯一片段为历史 runner 做受信暂存适配；与旧重复身份适配组合，保留合同和原始字节，未知 runner 不放行。
3. [x] 启动故障事实：增加可空 failure_json、结构化已知准备错误、有限公开投影和原子事件。绑定真实授权启动边界，覆盖旧 work.generation 的恢复尝试及迟到竞争。
4. [x] 控制与调度：保存工具回执后可信交接、故障优先收尾、临时恢复和确定问题需处理、手动重试及重启恢复。成功启动才解除当前错误，人工动作和所有既有门禁继续优先。
5. [x] 页面：当前任务、历史及详情展示同一原因、时间、次数、阶段和重试安排；直接呈现未启动／启动失败／恢复失败，不增加轮询。
6. [x] 本地链路验证：真实 Python／Node／SDK 工具回执、真实 SQLite／API／SSE、禁网容器 Cerberus 环境与完整回归，以及两个空间的真实 Chrome 明暗／窄屏检查。
7. [x] 核对操作说明与实际 diff，执行 trellis-route(target=check) → full Check-All，完成规范更新；无待处理 CHK／FBK，DOC-001 已修复。
8. [x] trellis-push 精确文件计划已获确认，业务提交推送完成；任务记录与完成态由本次收尾提交同步。

## 关键场景矩阵

| 场景 | 必须验证的结果 |
| --- | --- |
| 旧 profile=3.12.15、实际3.12.16 | 默认兼容；实际依赖准备、启动及冻结回归可以继续；两版本各自留证 |
| 同版本、跨主次、exact、非法版本及探测失败 | 明确放行或拒绝，期望／实际／策略一致，缓存不能绕过 |
| 缓存由旧运行时创建后命中 | 每次准备仍核对实际版本；不复用不兼容证明；不覆盖源码和会话 |
| 冻结 runner 的已知／未知来源、与重复身份适配组合 | 只接受已核字节；原合同、节点、插件和结果保护保持 |
| 启动失败但 Pi settled | failure 持久，当前和历史原因可见，不能变成正常结束 |
| 同故障多次显式尝试、重启、成功恢复 | 次数真实累计且不因重启归零；成功启动才解除，历史留档 |
| 原 work 代次较旧 | 当前合法控制者的恢复失败可记录，旧代迟到写入被拒绝 |
| 暂时资源占用／确定不兼容 | 前者持久等待并按策略重试；后者停止模型空转，修正后手动恢复原目标 |
| 人工暂停／停止与失败／恢复竞争 | 迟到结果不重开计划、不更改新代次状态；成果和输入事实保留 |
| 两空间、旧记录、异常HTML、刷新与SSE | 同一合同，旧记录正常读，页面转义、时间和原因准确，配置编辑不被推送覆盖 |

## 验证命令

在实际新增测试模块确定后将名字同步到本计划，避免机械运行不存在的模块。已有定向入口：

```bash
PYTHONPATH=orchestrator .venv/bin/python -m unittest test_project_scenario_content test_account_runtime test_projects_workspace test_project_native_regression test_project_native_verifier
PYTHONPATH=orchestrator .venv/bin/python -m unittest test_projects_agent test_projects_schedule test_projects_schedule_edges test_projects_single_objective test_projects_engine_cycles test_projects_pi_round test_projects_store test_projects_verification_recovery test_projects_runtime_resilience test_project_duplicate_adapter
node --check webui/projects.js
node --test images/pi-agent/host.test.mjs
.venv/bin/python deploy/v3/verify_pi_projects_browser.py --evidence .deploy/projects-runtime-resilience/projects-browser
.venv/bin/python deploy/v3/verify_warmup_pi_browser.py --evidence .deploy/projects-runtime-resilience/warmup-browser
git diff --check
```

- 业务链：用现有本地镜像运行冻结 Cerberus 原版与参考实现，记录 profile=3.12.15、实测3.12.16 的环境准备和完整原生回归；负向候选仍被拒绝。使用现有 ProjectVerifier 真实入口及来源适配，不能只模拟版本函数返回 True。
- 页面链：复用浏览器脚本的真实 API／SQLite／SSE 驱动合成启动失败、计划等待、刷新、重启和成功解除；截图报告写项目忽略的证据目录。
- 检查通过后不重复无变化的大套验证；新增改动或失败再定向复验。未执行的真实模型、生产交付和完整跨平台验证明确保留为未验证。

## 风险与恢复点

- 历史回归控制器多版本、摘要或片段不符：停在可见环境错误，不猜测替换、不改冻结资产。
- 持久故障和原代次／人工动作冲突：以当前所有者及取消事实为准，失败不能变成自动解除强门禁的理由。
- 准备故障包含私有信息：只公开模板及白名单事实，真实异常仅保留有限安全信息。
- 本地镜像或浏览器不可用：定位实际依赖并记录验证限制，不以纯 mock 声称完整链路通过。
- 生产状态与规划时快照不同：交付时重新只读核对，不复用旧截图或旧 next_run_at 操作在线任务。
