# 修复验证记录

## 环境与边界

- 验证根：`.deploy/project-iteration-repairs/`（gitignored）。Python 依赖使用该目录下的独立 `venv`。
- 最终本地镜像清单：`manifest.json`，release `project-repairs-local-20261021-e`。control/account 均由当前源码快照生成，Rust 使用正式构建参数；不发布镜像、不切换生产。各运行场景证据目录保存相应清单副本，复用证据的源码差异见source-reuse-final.json。
- 所有账号、模型响应及用量均为合成数据，真实模型请求为 0。既有生产展示和本轮以外资源不在清理范围。

## 确定性与回归验证

| 验证 | 实际结果 | 证据 |
| --- | --- | --- |
| 修复前新增故障回归 | 7 项全部暴露原缺陷（4 failures、3 errors） | `regression-before.log` |
| `PYTHONPATH=orchestrator venv/bin/python -m unittest test_project_plans` | 28 项通过 | `plan-tests.log` |
| `test_project_iterations test_main test_run_windows test_run_window_scheduling test_warmup_quota` | 149 项通过 | `backend-tests.log` |
| `unittest discover -s deploy/v3 -p test_manage.py` | 26 项通过 | `manage-tests.log` |
| 收口消息与终态定向复验 | 2 项通过 | `settle-followup.log` |
| 新额度代次、清理中自然终态、重复局部阻塞 | 3 项通过；其中前两项为补充测试 | `stop-epoch-tests.log` |
| 重新读取后、SQL认领前的独立连接终态竞争 | 补充修复前确定性失败；增加SQL状态条件与认领检查后，5项停止回归通过 | `stop-claim-before.log`、`stop-claim-after.log` |
| 最终源码六组完整后端回归 | **180项通过，281.543秒** | `final-backend-tests.log` |
| `node --check webui/app.js`、`git diff --check` | 通过 | 命令返回码 0 |

定向复验与前面完整套件有重叠，不能相加冒充独立测试数量。新增额度代次与清理中自然终态两项在首次 28 项计划套件之后加入。

## 真实运行验证

必要的针对性验证已完成，以下保留实际过程；全库运行按用户要求提前停止，不计为全量通过。

- 首版镜像 a 的两次预检均在发送器入口失败，项目场景尚未进入。构建时误启用需额外 CA 文件的测试特性，已改回正式参数重建镜像 b。失败日志 `scheduling.log`、`scheduling-diagnostic.log` 保留。
- 镜像 b 首次运行通过网关／发送器预检、双 CLI 并行、冻结兄弟继续执行及逐步 11/22 合成 token 对账。新增局部故障夹具在后续项目仅发布目录、尚未完成实际启动时暂停，触发既有启动门禁，场景判为失败。证据 `scheduling-b.log`、`scheduling-b-evidence/`。
- 夹具已改为首步独立接受后注入局部故障，并等待后续项目首步接受才暂停；不放宽产品启动门禁。镜像 b 的第二次调度复验使用 `scheduling-c.log`、`scheduling-c-evidence/`。
- 镜像 b 的第二次调度复验完整通过，退出码0，包括真实60秒超时接续及普通Tasks并行／透传长连接保持。
- 最终SQL认领补充修复后，镜像 c 调度复验**全部通过，退出码0**。证据 `scheduling-final.log`、`scheduling-final-evidence/`，包括发送器／网关及容器隔离预检、双CLI两步11/22用量、局部blocked原因与健康补位、真实60秒超时原会话接续、普通Tasks容量2及透传长连接保持；验证容器已按本轮标签清理。
- 镜像 c 的旧单步兼容场景**通过，退出码0**。证据 `iterations-final.log`、`iterations-final-evidence/`；实际Scheduler／driver／tmux、原生主会话、严格释放与独立Docker验收完成两步累计，同一目录保留，未启动项目仍无目录。
- 项目浏览器场景已通过，退出码0，证据 `browser-project-final.log`。

## 浏览器视觉复核补充

- 项目浏览器场景通过、退出码0，七状态渲染／下一投放隐藏、SSE保持、目录跨重启、XSS及1280/390px明暗主题均通过。截图已保存browser-evidence/并查看390暗、1280明。
- 时段最初浏览器脚本退出0，但视觉复核发现390px弹窗内部横向滚动；旧断言只看document宽度，不能作为无溢出通过证据。
- 增加form／fieldset滚动宽度及每个控件的内部边界断言后，镜像c确定性失败：formOverflow=true、optionsOverflow=true、controlsInside=false，同时document overflow=false。证据browser-window-before-responsive-retry.log及browser-evidence/before-responsive-*.png。
- browser-window-before-responsive.log在进入页面前因共享宿主瞬时内存不足被正式预检拒绝；未绕过门禁。构建结束、内存恢复后使用清单c的持久副本重试，才获得上述布局失败。
- 新镜像d仅改变webui/style.css（已按文件摘要比较c/d构建上下文）；改为明确的可收缩网格，窄屏时间控件单列。后端／driver／JS／模板等源码与c逐字节相同，沿用对应既有通过证据。
- 镜像d时段首轮复验在后续导航阶段超时，证据browser-window-responsive-final.log。
- d的首轮内部边界全部通过，但保存后立即切页出现浏览器等待超时；源码显示弹窗先关闭、旧列表刷新仍在执行，可能与导航竞争。夹具等待保存回调结束后完整复验退出0（browser-window-responsive-retry.log）。
- e将实际关窗移到列表刷新完成之后；最终浏览器恢复立即切页，并断言关窗时提交已结束，完整通过退出0（browser-window-e-final.log）。最终四张时段截图已复制browser-evidence/，390暗与1280明已查看。
- 对c/e全部896个构建文件比较：仅webui/app.js与style.css变化，Dockerfile只有release标签变化；后端／driver／Rust等未变。source-reuse-final.json保存两版清单与比较结论，沿用相应通过证据。
- 单批规模e已按用户要求停止，证据catalog.log、catalog-evidence/；部分覆盖见下文，不计全量通过。

## 用户调整后的验收边界

- 用户最新要求“这个太慢了吧，我们看着情况测吧”，本轮改为依据已观察运行情况和关键场景验收，完整100×20不再作为阻塞条件；三件套与Brief同步该决定。
- 已保存停止前的SQLite一致快照：单批完成**8个项目、184步接受、无重复接受、实测CLI上限2**，正常Run未报告失败。catalog-evidence/catalog-partial-result.json明确full_catalog_passed=false；没有完成全库／全会话原生审计，不宣称2000步通过。
- 用户中断时发现临时目录删除与活跃容器写入竞争，首次退出附带Directory not empty。容器／网络清理完成后，已精确删除本轮残留目录，catalog-evidence/cleanup.json记录0容器、0网络及临时根已删除。
- 验证脚本已修复中断清理顺序。独立受控SIGINT验证退出130，cancel-cleanup-evidence/cleanup.json确认0容器、0网络、无临时根，不再出现目录竞争；这是预期中断验证，不计为产品失败。
- 原生输入／逐步用量、会话保持及终态保护沿用已通过的确定性与真实短场景；180项后端、26项管理、调度／旧单步Docker及两个浏览器场景均有对应证据。
- 已通过Phase 2.1的Pre-Check进入当前会话全面Check-All，复用有效验证证据，不重跑完整长测。
