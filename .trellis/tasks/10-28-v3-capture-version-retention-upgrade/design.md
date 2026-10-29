# 技术设计

## 配置权威与页面

- 拟在 accounts 增加可空的 `claude_code_version`，以及默认 0 的 `projects_capture_enabled`、`warmup_capture_enabled`，按既有 `_ensure_column` 方式幂等升级；版本校验复用 `_normalize_claude_code_version`。
- 拟新增 `GET/PUT /api/accounts/{aid}/cli-settings`，读取配置、有效版本与来源；保存只更新显式提交的字段，null 清空账号版本，缺失字段保持原值。校验账号存在且未删除，沿现有管理鉴权，不唤醒环境或启动模型。
- 账号页提供版本配置；项目与养号共用页面组件增加配置按钮，弹窗显示同一账号版本及当前空间抓包开关。抓包默认关闭，另一个空间的值不能被本页保存覆盖。
- 复用当前模态、escapeHTML 与异步归属校验；换账号、换空间、关闭窗口及旧回执返回时不串值，未保存输入不被实时刷新覆盖。

## 统一版本解析与冻结

- 保留 `effective_claude_code_version()` 的全局职责；增加具有账号上下文的解析层，实现“单次显式值 → 账号配置 → 全局有效值”。非法覆盖直接报错，不能用宽泛异常捕获掩盖成全局回退。
- 普通/批量 run、运行抓包、旧养号、新 Pi work、兼容项目计划及其 CLI 评审均在确定账号并创建执行身份时解析一次，写入现有 runs.claude_code_version、settings_json 或 execution_json。排队/恢复使用已保存值。
- `_project_execution_settings()` 及 Projects/旧项目管理器的无参 settings 回调接入已核账号；保留已有 execution_json，不在评审或恢复时再次从当前默认值解析。
- 新登录、重授权使用账号版本；LoginSession.version、持久草稿 version 及现有显式恢复参数保存原选择。尚无账号记录的新草稿沿全局值冻结，不能在 commit 或重连时改用当前设置。
- 续聊优先原 run/会话非空快照。旧空快照按既有一次回填模式扩展：优先可核对执行记录中的版本，否则按账号继承取值，持久化后保持稳定并显示回填来源。
- 所有 `_claude_exec_env` 调用核对实际选择；PATH、安装准备和子命令环境使用同一已解析值。CLI 维护命令沿原调度和额度门禁，不新增主动模型或 usage 探测。
- 只读身份/进程观察保留实际版本及证据，不把当前账号默认值伪装成已运行的版本。API-only transport 不因查询版本安装或唤醒 CLI。

## 抓包认领与逐作业监督

- 关闭时保留 PiTerminal 当前共享 CLI、passthrough 和逐 source 监督，不改变普通并发能力。
- 开启时采用已存在的 CLI 专用独占认领：`shared_cli=False, exclusive=False`，对应 gateway 的 `prepare-cli`；等待兄弟 CLI 退出，独立 API 不被排空，不改 cc2api 租约协议。
- 现有 PiTerminal 将“共享租约”和“有独立监督进程”耦合，不能简单删除检查。为捕获执行增加可识别的监督角色，复用 process/source/PID/started 证明、逐作业 tmux socket 和启动许可；实际租约仍如实记录为 CLI 独占，不伪装成共享或私有评审。
- 监督/控制/收尾的能力判定同时支持共享 Pi 作业和本账号独占捕获作业；评审原有私有容器与串行资源逻辑保持。单执行恢复路径补齐必要的 settings_override、network_inspection_mode 与监督字段。
- 捕获在认领后配置唯一 Recorder 上下文、CA 和分代输出，匹配 capture/QUOTA_SOURCE/进程 ACK 后才启动 CLI；默认关闭和普通 API 不注入抓包 CA。
- 停止时先凭内核证明收口本作业，再有界收尾 Recorder、核对已落盘产物、恢复 passthrough 并释放租约；共享作业收尾不重置兄弟监听。无法证明收口时沿现有 cli_reconcile 保护，保留健康 API，不删除证据。

## 证据读取与停止状态

- 运行抓包复用 `/api/runs/{rid}/capture` 与现有 stop API。项目/养号在共用 router 拟增加 `/work/{work_id}/capture` 及受限文件读取入口，分别使用两个已有服务前缀。
- 读取从服务端 work→账号→workspace/flows→execution 登记派生路径；可选执行筛选必须属于该 work，不把 work ID 当 run ID，也不接受任意宿主路径。
- 复用 execution_flows() 与当前源/代次隔离；两个迭代空间的抓包开关在新执行认领时读取并记录，开关改变不覆盖正在运行的上下文或原版本快照。
- 展示采集中、部分、未采到及异常状态；没有完整索引时仍列出已有文件。保留旧平铺与分代读取，容忍尾部未完成记录但不截断原文件。
- Recorder 尽量优雅完成索引发布和文件关闭；强制退出保留已持久化 JSONL/stats/.flow，真实中断状态不伪装成完整响应。已有约 2 秒后强制收口的路径必须单独验证。
- 运行、项目/养号业务停止或暂停继续沿各自现有语义；新增抓包不承诺恢复原进程。保持详情轮询/长连的关闭释放，以及旧会话和工作区。

## 身份兼容与回退

- CLI 缓存已有精确安装、实际版本校验及原子 ready，无需版本专用镜像。选择某版本不代表自动升级网关 UA/请求画像或访问允许范围。
- 本地身份映射当前仅直接登记 2.1.293，其他版本可使用已有真实请求观察；对任务验证所用精确版本补充可核对的官方 CLI 隔离证据，未知来源明确报错，不猜字段或改设备身份。
- 新字段缺省保留全局/抓包关闭的旧行为；已保存非空版本、账号身份、草稿、会话及有效历史产物不重写。
- 回退可停用新入口与捕获分支，保留兼容的新增列及产物；不通过清库、改原报告或删除 flows 回退。

## 实施补充

- 新增 `runs.claude_code_version_source` 随版本创建或兼容回填，来源为 explicit/account/global 或 legacy-*；旧空快照优先使用来源、容器和环境代次都匹配的原执行登记。
- 网络 ACK 增加 previous_listener_graceful，捕获目录写 capture-status.json；CLI 已停止或被移除时，恢复使用已核环境行定位独立网络角色，保留 API。
- Recorder 在请求体可读时追加 pending，正常响应为 complete，错误或停止为 interrupted；停止后的迟到 response 可追加新字节，但不能覆盖中断事实。索引按 flow_id 更新，完整 JSONL 按事件只追加。
- 两迭代空间的受限预览 API 为 `/work/{work_id}/capture/file?path=...`，仅开放脱敏索引和收尾摘要，完整 HTTP 与 .flow 只列文件元信息；查看窗口手动刷新，无额外常驻轮询。
