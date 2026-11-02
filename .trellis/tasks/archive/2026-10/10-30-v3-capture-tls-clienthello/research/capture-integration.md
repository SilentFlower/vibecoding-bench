# Research: 抓包入口、执行归属与受限预览集成

- Query: 最少修改哪些入口，才能让 `tls_clienthello.jsonl` 关联冻结 CLI 版本、source、run/work、连接及 HTTP flow，并保留旧证据、私有原始握手和健康独立 API？
- Scope: internal
- Date: 2026-10-30

## Findings

### 1. 已确认的现有契约

已读取当前任务 `prd.md`、`.trellis/workflow.md` 的研究/设计阶段、下列相关规范，并追踪实际实现。本文只研究接入，不决定 ClientHello 解析器及 JA3 算法细节，不改 cc2api TLS 模板。

- `.trellis/spec/vibecoding-bench/backend/account-runtime-v3.md:885`：CLI 版本冻结、Projects/warmup 抓包开关、分代路径、受限预览和收尾契约。
- 同文件 `:68`、`:85`、`:916`、`:918`：捕获独占 CLI，不排空独立 API；API 请求不经过 CLI 网络监听；共享 passthrough 不能重启兄弟监听；收尾不确定时保留证据并隔离 CLI。
- `.trellis/spec/vibecoding-bench/deploy/official-protocol-capture.md:139`：原始 HTTP、flow、debug 在私有目录，目录 `0700`、文件 `0600`；公开材料不复制秘密。
- 同文件 `:167`：HTTP 正文视图与 wire 字节、上游 TLS 与 CLI 原生 TLS 的边界。新增证据应明确是 **客户端到 Recorder** 的 ClientHello。

### 2. 真实入口与冻结数据来源

| 场景 | 真实来源与冻结版本 | 最小注入位置 |
| --- | --- | --- |
| 普通 capture，旧 sidecar | `Runner.start_run`，`main.py:3968`；版本经 `_resolve_run_claude_code_version(task.get("claude_code_version"))`，`:4006`；`source=run:{run_id}:{attempt}`，`:3911`、`:4055` | `sidecar_env` 在 source/version 均确定后附加 `CAPTURE_CONTEXT`。当前 worker 有 `CLAUDE_CODE_VERSION`，sidecar 没有这项版本归属，不能从默认全局推断。 |
| 普通 capture，v3 | `AccountRuntimeV3.start_run`，`account_runtime.py:1323`；明确 `run_id` 参数，实际启动版本来自 `worker_env["CLAUDE_CODE_VERSION"]` | `context=dict(quota_env)` 及 `context.update(...)`，`:1411`。不要事后读取已变化的账号/全局版本。 |
| Projects / warmup | 共用 `PiTerminal.start`，`pi_terminal.py:63`；版本为 `json.loads(work['settings_json'])['claude_code_version']`，`:71`；source 为 `{namespace}:{work['id']}:{work['generation']}`，`:74` | 捕获分支 `context.update(...)`，`:119`；明确传 `namespace`、`work_id`。**`:107` 的 `job['run_id']` 实际存 work ID，仅供作业兼容，不能作为 runs.id 写入握手。** |
| capture 续聊，v3 | `Runner.start_continue`，`main.py:4355`、`:4368`；source 为 `continue:{sid}:{generation}`。`begin_continue` 的版本来自原 run 快照，`account_runtime.py:2470`；真实 run ID 是 `run['id']` | `begin_continue` 捕获分支 `context.update(...)`，`:2494`。source 中第二段是续聊 sid，不能从它推断原 run ID。 |
| capture 续聊，旧 sidecar | `Runner.start_continue`，`main.py:4411` 来源；`:4415` 捕获环境；`:4427` 原 run 冻结版本 | 版本确定后向 sidecar 环境加同一上下文。无需改续聊分代/目录规则。 |

`main.py:1973 _resolve_account_cli_version` 的已有版本来源值为 `explicit/account/global`；`main.py:2002 _resolve_run_claude_code_version` 对旧空值有回退。握手元数据记录本次真正装载/启动的版本；`claude_code_version_source` 仅在上游有真实冻结值时传递，不凭空填 `global`。Pi 以真实 settings 快照为准。

主会话已选定一个环境键 `CAPTURE_CONTEXT`，JSON 对象 `schema=1`，避免新增一组平行环境键。建议内容：

- 必需执行归属：`schema`、`source`、`claude_code_version`。
- 普通/续聊：真实 `run_id`；续聊仍保留当前完整 source。
- Projects/warmup：`namespace`、真实 `work_id`；不伪造 run ID。
- `claude_code_version_source`：仅有冻结来源时附带。

这些是**本次新增字段约定**，不是现有数据库/mitmproxy 的字段。版本表示执行所配置并实际使用的 CLI，不证明每一条连接都由该产品版本发起；启动探测、curl 等流量也可能经过捕获监听，尤其 `CAPTURE_SCOPE=all`。缺少/无法验证的元数据应明确为 `null` 或未知状态，不猜测当前默认版本；上下文问题不应阻断 TLS/HTTP 转发。无需把账号令牌、账号邮箱、完整工作配置写入元数据。

### 3. 网络上下文的必经白名单

`images/account/network-context.py:193` 的 `permitted` 明确列出可传给 Recorder 的键，`:197` 会丢弃未列出的上下文。**只在 orchestrator 增加字段，不改此白名单，会静默失效。** 最少增加 `CAPTURE_CONTEXT`。

`network-context.py:207` 用 `mitmdump -s /sidecar/recorder.py` 启动独立监听；普通 sidecar 的 `images/sidecar/start.sh:107` 直接继承容器环境。v3 分支 `start.sh:99` 再通过 network-context，所以两条入口都需覆盖。

TLS 文件建议从已有 `CAPTURE_FILE` 的父目录派生 `tls_clienthello.jsonl`，仅在现有 full capture 开关开启时写。不新增独立启用开关，也不把文件固定到账号共享 `/flows/tls_clienthello.jsonl`。这样 HTTP/TLS/flow 天然落在同一个真实执行目录。

**打包易漏点**：`images/v3/Dockerfile:87` 已 `COPY images/sidecar /sidecar`，新增 sidecar Python 模块会包含；旧 `images/sidecar/Dockerfile:36`–`:38` 逐个 COPY `start.sh`、`recorder.py`、`quota_protocol.py`。若 Collector 新建辅助 Python 模块，旧 Dockerfile 必须同步 COPY，避免旧 capture 启动时 ImportError。两种镜像均固定 mitmproxy `11.1.3`（sidecar Dockerfile`:20`，v3 Dockerfile`:82`）。

### 4. 流目录、HTTP 关联与兼容

`account_runtime.py:1957 execution_flows` 将兼容路径映射为环境私有 `flows/group-<sha256(relative)[:20]>/executions/<sha256(source)[:20]>`，组与执行目录均 `0700`（`:1970`、`:1974`）。不要绕过此方法另建 TLS 路径，不迁移或清理旧证据。

`recorder.py:282 _capture_record` 当前只保存 `ts/flow_id/request/response/analysis/classification`，没有连接 ID 或冻结执行版本。`recorder.py:310 _capture_index_entry` 显式重建字段，故必须在原始 HTTP 记录和轻量索引中同时加入 `client_connection_id`。主会话指定与 TLS hook 的 `data.context.client.id` 对应，HTTP 侧为 `flow.client_conn.id`；精确 mitmproxy API 已交由 Collector 研究核验，不能将 `server_conn.id` 当成原生客户端连接。

- ClientHello 发生时还没有 HTTP flow，TLS 记录以客户端连接 ID 关联，不能编造 `flow_id`。
- 一个客户端连接可有多个 HTTP 请求（例如 HTTP/2），HTTP 索引多条记录共享连接 ID 是正常情况。
- 原始/轻量 HTTP 记录可附同一个执行上下文快照，使脱离目录的单行仍可判断归属；不要把原始握手放入 HTTP 轻量索引。
- `analysis.cc_version` 是从 HTTP billing 等观察得来的产品字段（`recorder.py:272`–`:278`）；现有 `index.cc_versions` 从它聚合，不等同冻结执行版本，不能用新增版本覆盖它。
- 老 HTTP 行和旧索引无连接字段时保持可读，返回缺省/空值即可；老目录不存在 TLS 文件不是错误，也不能伪造 `tls_clienthello.jsonl`。
- 同一 source 重试可能复用相同执行目录；Pi 启动 handle 是随机 UUID，但执行目录按 source 哈希。新握手必须追加，不能重建文件抹去前次字节；本任务不应扩大成执行目录重构。

现有 HTTP scope 不完全一致：普通 Runner capture 设置 `CAPTURE_SCOPE=all`（`main.py:4021`）；Pi 捕获上下文未设置 scope（`pi_terminal.py:119`），沿 Recorder 默认 `anthropic`（`recorder.py:23`）。HTTP `_should_record` 可用 host/SNI 或路径兜底（`:144`）；TLS hook 先于 HTTP，不能直接使用 HTTP 路径筛选。需要明确 TLS 的无 SNI/非目标 SNI 策略，且不得顺手改变现有 HTTP 采集范围。

### 5. 文件列表与安全预览

`capture_artifacts.py:125 _capture_files` 递归列出非链接文件，只额外排除 `cli` 和 `passive-quota.jsonl`。TLS 文件**不需要新的列表分支便会出现**。索引未生成但已有非空 TLS 文件时，`capture_summary` 按现有规则可报告 `partial`（`:184`），不应冒充已有完整 HTTP 请求。

`capture_artifacts.py:197 capture_file_preview` 目前仅允许 `capture_index.json` / `capture-status.json`（`:205`），并要求相对路径属于当前证据组文件清单（`:207`），拒绝 `..`、绝对路径和组内 symlink。新增 TLS 预览必须复用这些归属校验，并独立做 JSONL 逐行解析及明确字段白名单，不能把原 JSONL 对象原样返回。

建议公开：schema/时间、执行上下文的安全字段、`client_connection_id`、方向、解析状态、JA3 串/哈希、公开数值 ID 的有序列表、key_share 的组/长度，不含字节。SNI/ALPN 是否展示按最终白名单确定。原始握手 base64、原始扩展 payload、session/ticket、PSK identities/binders 等全部留私有文件。嵌套字段也需逐字段重建，不能只删顶层 `raw`。

预览应限制读取总字节、行数/单行长度；聚合摘要的预算也必须覆盖整个证据组，不能对无界历史文件逐个给完整预算。正在追加的半行、坏 JSON、超限行应产生固定可展示状态，不输出原始行、原始异常、绝对目录。旧文件缺可选字段正常。敏感 canary 应放进嵌套字段验证不会漏出。

现有路由差异：

- Projects/warmup：`ProjectsService.work_capture`（`projects.py:1062`）先按服务空间查 work、账号、环境，再从 `namespace/work_id` 哈希取得证据组；相对文件委托 `capture_file_preview`（`:1092`）。`projects_api.py:162` 已有 `/work/{work_id}/capture/file`，不必另开任意路径下载 API。
- 普通 capture：`main.py:11899 GET /api/runs/{rid}/capture` 已 `_require_visible_run` 并核对 `run_kind=capture`，仅返回摘要/列表；当前**没有**普通 run `/capture/file` 路由。
- `webui/app.js:2011 renderCaptureDetail` 三入口共用。`:2033 fileRows` 目前只是文件名和大小的 `<div>`，**不存在可点击预览按钮，也不存在仅允许 index/status 的前端按钮白名单**。`:2121` 普通 run detail 与 `:2671` work modal 均调用此函数。`:2663` 已区分 `/accounts/warmup/pi` / `/projects` 的 work URL。

**主会话已收敛的最小展示方案**：在 `capture_summary` 增加有界、字段白名单的 `tls_clienthello` 摘要，由共用 `renderCaptureDetail` 直接展示安全 JA3/字段，覆盖普通 run detail、Projects 和 warmup 弹层；不建设文件浏览器，不新增普通 run file route。Projects/warmup 已有 capture/file 可增加 TLS 白名单，复用同一安全 parser。文件列表保持仅名称/大小即可，摘要可直接读到且原始数据无公开下载。这样实际三入口可见性由既有摘要 API 承担，避免新增一套 run 路由权限逻辑。

### 6. 并发、归属与 Recorder 生命周期防线

- `CAPTURE_CONTEXT` 在 Recorder 启动时解析为固定快照；不要每个 hook 读会被下一作业替换的 `context.json`。上下文 `source` 应与 `QUOTA_SOURCE` 核对；错误上下文不能静默标成另一执行/版本。
- 当前 `_configure_network_context` ACK 只核 `QUOTA_SOURCE`、模式、process kind（`account_runtime.py:1705`），网络侧 ACK 同样只有这些及 pid/start/graceful（`network-context.py:227`）。可附加捕获上下文规范化摘要并核对，避免“source/mode相同但元数据陈旧”通过。若本轮不加摘要，必须至少验证环境白名单真实传递和 Recorder 启动快照，不声称已有 ACK 证明版本匹配。
- 元数据是执行归属而非逐连接客户端身份；明确 `client_to_recorder`，不把 Recorder→upstream 的 TLS 重新标作 CLI 指纹；未知客户端无需猜测产品身份。
- 遵循现有 `_persist_capture` 非阻断模式（`recorder.py:440`）：解析/写盘异常固定错误信息，保留已写数据，不抛出中止 HTTP/TLS。当前通用 `_jsonl_append` 只是 `open(...,'a')`（`:51`），**不能假设它保证新 TLS 文件 `0600`**；新增原始文件需显式私有权限并验证。
- CLI→Recorder 捕获开始：v3 普通 capture、Pi 捕获、续聊都会调用 `_configure_network_context`，在 CLI 真正启动前切换/确认监听；它定位 network role（`account_runtime.py:1684`），不应为新 TLS 字段重建 API/整个环境。
- 捕获结束/停止/失败：`_finish_capture`（`:1822`）先发布 stopping，再切 passthrough；`previous_listener_graceful=True` 才 closed，强杀/未知为 partial，失败为 error，原文件保留。为新 TLS 补充 finalize 不可提前截断 HTTP 收尾。
- 普通非捕获共享 CLI：`:1431`–`:1439` 复用 passthrough；存在兄弟作业时 `require_reuse=True`。不得为了发布 Collector 热切这个监听，不能覆盖兄弟 source。
- 当前布局下 API sender 独立且不走该监听；部署/捕获切换只能更换 Recorder/network 的必要部分，不能把健康 API SSE 排空。老活跃环境的文件不会因新镜像自动刷新；应沿项目既有空闲更新/核对规则取新镜像，不为一次验收强制中断现存工作。

### 7. 最少产品文件范围

| 所有权建议 | 文件 | 必要改动 |
| --- | --- | --- |
| Collector | `images/sidecar/recorder.py`，及可选新 helper | 捕获 hook、固定执行上下文、私有 JSONL、非阻断异常；HTTP 原始/索引连接 ID。 |
| Collector | `images/sidecar/Dockerfile` | 仅新增辅助模块时补 COPY；v3 COPY 已涵盖。 |
| 入口/预览 | `orchestrator/main.py` | 普通及续聊 sidecar 元数据；既有 run capture 摘要自然获得公共安全 TLS 摘要。 |
| 入口/预览 | `orchestrator/account_runtime.py` | v3 normal/continue capture context；如采用则核对上下文 ACK 摘要。 |
| 入口/预览 | `orchestrator/pi_terminal.py` | Projects/warmup 元数据快照，明确 work 而非 run。 |
| 入口/预览 | `images/account/network-context.py` | CAPTURE_CONTEXT 白名单、如采用则 ACK 摘要。 |
| 入口/预览 | `orchestrator/capture_artifacts.py` | 保持递归列表；同一有界白名单 parser 供 TLS 摘要与既有受限 file 预览复用。 |
| UI | `webui/app.js` | 三入口共用安全 TLS 摘要展示，保留既有异步归属保护。 |

`images/sidecar/start.sh` 现有继承环境/分支已足够，无新增开关时不必改；`projects.py` / `projects_api.py` 现有路由与归属可复用，无需重写服务查询。无需新增数据库列、移动历史目录或修改 cc2api。

### 8. 定向验证建议（本研究未运行测试）

现有测试应扩充关键断言，新增只覆盖本次真实行为的用例；不把 Mock 通过当作真实 mitmproxy hook 验收。

1. `images/sidecar/test_recorder.py` 的 `RecorderQuotaTests.test_capture_persists_request_before_response_and_marks_interruption`、`test_capture_response_updates_index_without_double_counting_request`：保持 pending/complete/interrupted 和 HTTP 统计；新增 HTTP 原始/索引连接 ID 一致、一个连接多 flow、旧无连接 fixture 兼容、写 TLS 失败仍能处理请求。
2. `orchestrator/test_capture_settings_runtime.py` 的 `CaptureSettingsRuntimeTests.test_capture_and_passthrough_use_distinct_leases_and_exact_version`：对 Projects/warmup 各开/关，核 CAPTURE_CONTEXT 是冻结 `2.1.303`、source/work/namespace 正确、无假 run ID，关闭不启动 Collector。
3. 同文件 `test_repeated_start_uses_current_proof_and_preserves_previous_attempt` / `test_attempt_directory_collision_does_not_overwrite_old_proof`：上下文取当前执行，TLS 旧字节保留。
4. 同文件 `test_recorder_shutdown_retains_files_and_reports_forced_or_failed_close`：额外放入 TLS 私有原始文件，确认闭合 partial/error 不删改。
5. 同文件 `test_summary_lists_partial_files_without_index_and_never_follows_file_links`：TLS-only/半行/旧无 TLS 文件、文件/父目录 symlink 不泄露。
6. 同文件 `test_work_capture_routes_isolate_namespaces_and_restrict_previews`：同 work ID 跨 projects/warmup 不串；TLS 安全摘要/既有 file 预览可达、嵌套 raw/PSK canary 不返回；绝对路径、`..`、非清单文件、HTTP原始和flow仍拒绝。普通 run 通过既有 capture 摘要验证 TLS 安全字段，不新增路由。
7. `orchestrator/test_account_cli_settings.py` 的 `AccountCliSettingsTests.test_all_run_creators_freeze_account_version_and_single_override`、`test_old_empty_snapshot_is_filled_once_with_source`：设置变化不改既有 run TLS 元数据；显式 capture 与账号/全局继承真实匹配。
8. `images/account/test_network_context.py` 现有 `NetworkContextTests.test_listener_ignoring_term_is_killed`、`test_unknown_pid_is_refused_without_killing_process`：保留信号/未知 PID 防线；新增启动环境白名单传递，不能仅测 context 字典包含键。若增加摘要，覆盖旧/错 ACK。
9. `orchestrator/test_account_runtime.py` 的 `AccountRuntimeTests.test_execution_flows_preserves_flat_history_and_rejects_wrong_binding`、`test_shared_cleanup_and_restart_leave_api_container_running`、`test_shared_recorder_failure_preserves_api_and_fences_next_cli`、`test_api_transport_never_installs_cli_and_preserves_cli_reconciliation`：本次入口/收尾改动的定向生命周期回归。
10. 真 mitmproxy `11.1.3` 本地隔离测试：TLS1.2/1.3 实握手→HTTP，真实 ClientHello ID 与 HTTP ID 相同；TLS解析失败/写失败不阻断 HTTPS；记录冻结上下文；真实 helper 在两种镜像中可导入。独立解码/JA3 已交 Collector 研究，不以本报告代替。
11. 浏览器定向验证：普通 run、Projects、warmup 三入口共用详情实际显示 TLS 安全摘要与 JA3；切换工作/关闭弹层/刷新期间旧请求不能覆盖当前内容；原始 HTTP/flow/TLS 字节无下载按钮，旧数据无 TLS 不报错。

可复用的定向执行形态：

```sh
python3 images/sidecar/test_recorder.py
python3 images/account/test_network_context.py
python3 -m unittest test_capture_settings_runtime test_account_cli_settings
```

最后一条在 `orchestrator/` 下运行，使用项目规定的依赖环境；追加上述 `test_account_runtime.AccountRuntimeTests.<method>` 方法即可，无需重复整个昂贵测试矩阵。实际执行/依赖安装由实施者按当前项目环境确认。

## External References

本主题为内部集成研究，未联网、未调用生产 API、未连接真实模型、未修改线上状态。mitmproxy 原始 ClientHello API 与 JA3 外部证据由同任务 Collector 研究负责；此处只记录已确认的镜像锁定版本 `11.1.3` 与主会话指定关联字段。

## Caveats / Not Found

- 研究时普通 run 无 `/capture/file`，WebUI 无任何抓包文件预览点击；最终设计选用三入口既有 capture 摘要及共用安全展示，无需增建通用文件浏览器或普通 run file route。
- 版本来源是执行元数据，不是 TLS 客户端身份识别结果；已有 `analysis.cc_version` 必须保留原观察语义。
- TLS 发生在 HTTP 前，host/path 过滤不能原样调用；无 SNI/未知 SNI 的记录策略应由最终设计明确。
- 当前网络 ACK 不证明 CAPTURE_CONTEXT 内容，通用 JSONL writer 不保证 `0600`；实施时必须落实相应验证。
- 未运行定向测试；以上测试是基于真实现有测试名的实施验证建议。全文行号为本次研究时快照，其他 agent 后续编辑会改变行号。
