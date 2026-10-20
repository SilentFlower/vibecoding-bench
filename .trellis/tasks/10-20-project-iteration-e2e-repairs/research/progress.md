# 实施进度

## 授权与当前阶段

- 完整Brief展示后，用户回复“修复”；已task.py start，状态in_progress。
- 用户询问为何另建任务，已解释本地工作流要求并继续本任务，未重开规划。
- trellis-route(target=implement)恢复个人默认inline，当前主会话实施；未派发子代理。压缩恢复时使用route_state.py恢复，不能仅凭本笔记推断路由。
- 用户要求“太慢了，按实际情况测”，已改为针对性验证并停止全量，不以完整100×20阻塞；三件套与Brief已同步。实现、必要验证与全面Check-All已通过（3维度，CHK/FBK均0，DOC事实同步2项）；规范同步written。用户随后确认提交并推送，修复已按确认范围推送至origin/v3，未部署。

## 已实施

- 决定文件在临时fd完成root:1000 0640、完整写入与fsync后replace；普通JSON默认仍0600；相同决定不替换inode。
- driver对open后nlink=0有限重开，仍拒绝硬链接、符号链接、特殊文件与超大对象，所有fd关闭。
- 内部_stop_project_run接受已终态／已认领停止，公开API初始终态仍400；停止前重新读状态与quota_attempt，并以SQL状态＋代次条件认领、检查rowcount。未认领者不清理，最终停止写入也有条件保护，不伪造释放证明。
- 局部blocked与人工取消区分，原始错误保留，严格释放前不补投本实例，健康兄弟及队列后续继续。
- 页面七状态提示及失效下一投放隐藏；时段启用／星期控件布局修复，关闭禁用且保存原配置，重新启用恢复DOM输入。
- 真实Docker／Chrome验证扩展；新增verify_project_catalog单批100×20、生产默认10秒稳定等待，独立19000秒场景／20000秒外层截止、持久脱敏进度与逐项目审计。

## 最终验证环境

- Python：.deploy/project-iteration-repairs/venv/bin/python，依赖沿既有requirements安装，产品依赖未改。
- 最终清单.deploy/project-iteration-repairs/manifest.json，release=project-repairs-local-20261021-e；build-e.log，源码快照摘要09049b97ceda8fc85cda3a32522abaf60e76d90b0484a16625e4f404f69b9f90。
- c/e构建上下文896个文件已逐字节比较，仅webui/app.js与style.css不同（时段保存结束后关窗及窄屏网格）；后端、driver、Rust及项目渲染实现未变，复用对应c验证。证据source-reuse-final.json。
- 本地构建复用Rust缓存，但由当前cc2api源码正式参数重新编译gateway/sender；Python／driver／webui来自本轮源码快照，不发布镜像。
- 验证脚本从只读/source挂载运行，最终证据目录保存清单副本。.deploy/project-iteration-repairs/status.py <evidence-dir>只读查看进度，runtime.json记录runner与数据根便于跨会话恢复。

## 已通过的验证

- 最终六组后端完整回归180项，281.543秒：final-backend-tests.log。
- 管理工具单元26项：manage-tests.log；node --check、py_compile、git diff --check通过。
- 最终镜像真实调度退出0：scheduling-final.log、scheduling-final-evidence/；双CLI同Run/session两步及11/22用量、局部blocked原始原因与健康补位、真实60秒超时保留1/2和半成品／新Run原会话接续、普通Tasks共享容量2、透传长连接跨补位及清理保持。
- 最终镜像旧单步兼容退出0：iterations-final.log、iterations-final-evidence/；真实Scheduler／driver／tmux／严格释放／独立Docker验收两步累计，目录保留、未启动项目零目录。
- 项目浏览器退出0：browser-project-final.log；七状态真实渲染、终态无失效下一投放、SSE保持滚动／展开、API／SQLite与目录跨重启、1280/390px明暗及XSS；截图browser-evidence/已保存，已视觉检查390暗／1280明。

## 当前执行与下一步

- 最终Chrome时段场景退出0：browser-window-e-final.log。两尺寸×明暗主题截图保存browser-evidence/v3-run-window-fixed-*.png；390暗和1280明已视觉检查，弹窗内部无横向溢出；启停／保留、关闭无效编辑保存及保存后立即切页通过。
- 单批规模已按用户要求停止：8项目完整完成、184步接受、无重复接受，实测CLI上限2；停止前未出现正常Run失败。catalog-evidence/catalog-partial-result.json保存一致的SQLite只读快照统计，full_catalog_passed=false，未完成全库／全会话原生审计，不宣称2000步通过。
- catalog-evidence/cleanup.json确认精确部署容器／网络0残留、临时根已删除。首次中断发现TemporaryDirectory与仍在写入的容器竞争；run_local_verification.py已改为异常／中断先停生产者再退出临时目录。独立受控中断验证通过：cancel-cleanup-evidence/cleanup.json为0容器、0网络、无临时根，退出130为预期SIGINT，非产品失败。
- 后续不再自动运行完整100×20；默认10秒规模能力保留为opt-in。已通过的确定性180项后端、26项管理、真实故障／停止／超时接续及浏览器结果保留。
- Pre-Check为no-hold，trellis-route(target=check)恢复check-all-inline，主会话full检查通过。两份既有规范project-iterations.md／database-guidelines.md已补齐交接、停止和时段表单契约；差异、六节结构、符号和链接检查通过。Phase 3.4业务提交及推送已成功，按同次确认同步原任务完成记录；其余59个变更保留。
- 完整证据索引见research/verification.md；任务开始前的33个dirty路径保持，不混入修复。

## 失败证据与修正

- 最初7项故障回归在修复前全部失败：regression-before.log（4 failures、3 errors）。中间版停止认领独立连接竞争新增回归先失败stop-claim-before.log；增加SQL状态条件后5项停止定向回归通过stop-claim-after.log，已包含最终180项。
- 首版验证镜像a误启用需要额外CA文件的v3-verification特性，发送器预检失败、项目场景未进入；scheduling.log与scheduling-diagnostic.log保留。改为正式构建参数后镜像b/c预检通过。
- 镜像b首次新增局部故障夹具在后续项目仅发布目录时暂停，触发既有真实启动门禁；scheduling-b.log与scheduling-b-evidence保留。夹具改为首步实际接受后注入／暂停，不放宽产品门禁。同镜像完整复验scheduling-c.log通过；补充SQL修复后最终镜像c复验也通过。
- 所有失败只计失败，未拼接凑通过；本轮已结束容器均按精确部署标签清理，生产与无关资源保留，真实模型请求0。
- c时段首次自动断言虽通过，视觉复核发现390px弹窗内部溢出，故不计布局通过。新增内部边界断言在c确定性失败（browser-window-before-responsive-retry.log），d网格修正后边界及完整流程通过（browser-window-responsive-retry.log）。d首次在保存后立即切页出现旧列表刷新竞争；e将弹窗关闭移到列表刷新完成后，最终流程通过browser-window-e-final.log。详细历史见verification.md。
