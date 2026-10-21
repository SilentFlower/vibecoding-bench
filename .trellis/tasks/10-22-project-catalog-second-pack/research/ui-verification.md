# 第二批内容包页面核验准备

本文前半记录脚本准备与静态核验阶段：当时尚未启动浏览器或任何业务。当前已完成 run-001 运行中预览及最终现场全量UI核验；最终结果为1943项检查全部通过、60张现场截图，详情见末节。浏览器按defer模式未写browser-done；其后主会话在审计快照通过后已释放gate，harness归档清理完成。

## 实际接口与范围

完整读取首批 `browser/verify-browser.py` 390行，并读取真实 `webui/app.js` 的 `paintScenarioInstance`、`renderRunFollowups`、`refreshRunDetail`／`openRunDetail` 相关逻辑。新脚本位于 `.deploy/project-catalog-second-pack/browser/verify-browser.py`，只访问指定回环服务的GET／HEAD；外网及写请求在路由层拦截，鉴权token只从临时私有文件读取，不写入结果或异常日志。

读取本批最终fixtures的catalog身份和动态三stage数量，实际核10项目／45场景／107任务、v4-en及完整摘要，覆盖四新仓50唯一任务。每个实例等待精确iid的GET与该实例scene数据库ID；逐项核中文goal／kind、选中集合、完整metadata行数、真实状态与attempts，以及candidate／review角色用量逐格匹配API。桌面1280暗色与390px亮色分别截取全部四仓中文路线、各实际实例与角色用量；截图文件包含instance ID及batch，避免同名覆盖。每次执行使用独立证据子目录；已有result拒绝覆盖。

## 英文首问截图边界

使用真实DE-U01候选Run。完成Run详情首次展示后仍会补刷最终files，因此必须等待页面自身 `state.runDetail.rid`精确匹配、`seq>=2`、`timer===null`、`finalFilesPending===false`、files数组存在，再通过真实summary按钮展开“初始需求”。不写DOM、不伪造页面数据。

截图前后分别记录同Run／seq、details.open、pre可见性和完整API／DOM首问SHA；截图前还核实际files数与DOM显示数一致。若应用再次折叠，保存原现场截图和失败事实，不重写图或伪称通过。所有当前脚本截图明确 `live_run_verification=true/read_only_replay=false`；未来若必要只读回放，必须另行标明，不替换本次现场证据。

## 运行与gate

实际依赖已在本机核实：`/usr/bin/python3` 可导入Playwright1.58.0，Chromium入口 `/usr/bin/google-chrome`，版本143.0.7499.192。项目旧验收venv没有Playwright，不能把该venv当浏览器解释器。

等root通知真实运行已到browser-ready后执行：

```bash
python3 .deploy/project-catalog-second-pack/browser/verify-browser.py \
  --connection-file .deploy/project-catalog-second-pack/run-001/connection.json \
  --defer-done --hold-on-failure
```

默认输出 `.deploy/project-catalog-second-pack/browser/run-001/`；重验须用新的 `--output-dir`，且只能在本browser目录内，不覆盖旧结果。运行目录以root实际提供值为准。

**无论通过或失败，此命令均不会写 `browser-done.json`**。结果写入该输出子目录 `diagnostics/result.json` 与 `diagnostics/gate-pending.json`，保留真实服务现场；等待独立机制审计快照完成并收到root明确通知后，才可释放原有gate。不能因为浏览器通过而提前清理现场。

静态准备证据为 `browser/preparation.json`：AST解析及 `--help` 已通过，浏览器／模型／OAuth／业务启动次数均为零。实际UI通过数、截图数及API／SQLite交叉结论将以真实运行后证据更新，现不预填。

## run-001 运行中独立预览

已按root追加授权执行 `browser/preview-running.py`，只读取现有运行服务，不等同最终全链路页面验收。证据位于 `browser/run-001-preview/preview-result.json`，明确 `tasks_running=true/full_pack_verified=false/status=preview_complete_tasks_still_running`；没有写正式browser result passed，也没有写browser-done。

真实目录API／DOM核10／45／107及v4-en，四个新增项目共50条中文goal在路线真实可见，1280暗色及390px亮色均无页面横向溢出，保存10张现场图（目录2张、路线8张）。业务写请求0、完成的外网请求0、页面异常0；外网资源请求均在发送前拦截，未外发本地令牌。已实际查看目录1280暗色、dotenv390亮色、Tenacity1280暗色三张代表图，未发现中文布局或选择器异常。

此预览不检查整包全部任务通过，不检查最终英文首问展开截图；后两项仍等待真实browser-ready后按完整核验脚本执行，gate继续保留。


## run-001 最终现场全量核验

2026-10-22已真实观察connection的browser_ready_file存在、batch_ids完整三项后，自主执行既定脚本 `--defer-done --hold-on-failure`，进程exit0。结果为 **1943 checks／0 failed、60张现场截图、12个实例、114条选中路径／50唯一任务、238个Run角色记录、300个任务／评审角色用量组**；完整metadata行150。三stage的50／33／31任务实际选集均与冻结fixtures逐ID一致，所有选中任务passed，attempt_count均1。

核验真实目录v4-en、10／45／107及digest `600c930ff5d43986c4d841ee1612c4dbd83a318d7bd706b50666f7f8f116139d`；四新仓路线中文，实例逐任务kind／goal／状态／业务结果、工作与评审剩余预算、只读零checkpoint／修改接受标记均与API一致。238个实际Run的身份、状态和candidate/review类型逐一匹配API；300组角色用量逐格匹配页面与API，未执行任务保持null／不完整，不补零。桌面1280暗色与390px亮色均实际截图；切换实例等待精确iid请求与scene数据库ID，无同名旧表误读。

英文首问为DE-U01、实际Run `6e1311262fc7`、instance2／scene6。真实最终files补刷收口后seq=2、timer=null、finalFilesPending=false、实际与显示file_count均47；通过summary真实展开初始需求，截图**前后**details.open与pre visible均true、同rid与seq，完整API／DOM正文SHA均 `69572b736bb01bad020bb5f7a4bfbff17f009bb8fe0081089ca80e0cbe5a48a4`，742字符；首问包含冻结英文指令，无私有rubric正文。截图是原运行现场，`live_run_verification=true/read_only_replay=false`，没有只读回放补图或DOM伪造。pre是页面原有可滚动组件，完整文本由DOM及SHA核验，不声称截图静态画幅展示所有滚动内容。

业务写请求0、完成的外网请求0、页面异常0、意外dialog0；外网资源均在发送前阻断，本地token未外发。模型／OAuth调用0，页面用量来自明确mock，不能据此判断真实模型质量或实际成本。

证据为 `.deploy/project-catalog-second-pack/browser/run-001/diagnostics/result.json`；gate记录同目录 `gate-pending.json` 明确 `browser_done_written=false`。该记录保留浏览器结束当时尚未释放gate的事实；其后主会话在3126项独立快照审计通过后释放，harness退出0并归档清理，最终归档与快照对照通过。

已实际查看三张最终代表图：

- `browser/run-001/mock-live-english-first-prompt-instance-2-run-6e1311262fc7-1280-dark.png`：英文首问现场展开。
- `browser/run-001/mock-usage-2-python-dotenv-1280-dark.png`：任务与评审独立用量及披露两轮。
- `browser/run-001/mock-instance-2-batch-1-python-dotenv-390-light.png`：手机中文任务与两个独立接受检查点。
