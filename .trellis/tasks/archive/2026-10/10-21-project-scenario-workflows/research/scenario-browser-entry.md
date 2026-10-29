# Research: 新场景真实浏览器验证的最短入口

- Query: 复用现有执行链与本机浏览器，完成新场景 UI／API／SQLite 验证，避免手工填业务结果。
- Scope: internal，读取实际验证器、鉴权、页面选择器和依赖；仅研究目录提供草案。
- Date: 2026-10-21

## Findings

最短路径是在 `verify_project_scenarios()` 当前真实控制进程旁启动临时 HTTP 服务，让本机 Chrome 直接打开 main UI，由页面创建和启动 policy 3 批次。原 Scheduler、AccountRuntime、driver、候选封存、私有评审、严格释放及 tick 均复用，不另造业务结果。

### 已确认的本机能力

- `/usr/bin/google-chrome` 可用，实际 `google-chrome --version` 返回 `Google Chrome 143.0.7499.192`。
- `.deploy/project-iteration-repairs/venv/bin/python` 可导入 docker、requests、websockets、uvicorn、fastapi；没有 Playwright，现有脚本也不依赖它。
- 当前可调用工具中没有浏览器 MCP；现有 `deploy/v3/verify_browser.py` 已使用 Chrome 独立配置、原生 CDP 和 websockets，足够实现本项。
- `main.session_auth_middleware()` 实际要求 `Authorization: Bearer <V3_INTERNAL_TOKEN>`。草案按该定义发送，不新增 x-v3-service-token 或产品鉴权映射。
- `WEBUI_DIR=/source/webui` 可以直接使用本次源码。源码 index 的 xterm／字体为外部资源，Chrome 限制网络到回环后失败会记录；本次项目页不依赖终端组件。真实业务 JS 异常仍严格失败。

### 既有入口的真实边界

`verify_stack.py --browser --project-iteration` 目前只路由旧 schema 2 项目页面场景。`verify_project_browser.py` 在约第 82 行开始直接插入 timeout Run、plan、attempt 并写实例进度；其中已有说明这只是页面夹具。因此不能把此命令当作新场景执行和恢复的端到端证据。

`verify_visible_logout()` 已有 Chrome 传输代码，但固定先访问统一网关 `/login`，随后进入 iframe；不能直接拿它调用 main 根页面。此次草案只复用其已验证的 CDP 方式，不改该旧链路。

`run_local_verification.py --project-scenarios-only --scenario-capacity 1` 已可真实运行新场景机制，但目前没有浏览器、HTTP 服务或页面创建动作。它是本次最短接线基础。

### 可运行草案

文件：`research/verify_scenario_browser.py`。提供 `verify_scenario_browser(base, service_token, evidence_dir, ...) -> dict` 和独立 CLI。

已对照真实页面和 API 定义实现：

- 直接进入 `/#projects`，检查 2 个合成项目／2 场景／6 任务，初始无批次。
- 先核对新内容默认 600 秒，再通过真实表单改为候选 60、任务累计 180、评审 60／240，默认容量 1；调用表单正常提交，再点“启动自动推进”。
- 页面首问和实际调度都由原实现处理；草案不写 task、run、attempt、evaluation 或 checkpoint 结果。
- 等真实 API completed 后核 6 任务通过、仅 Q4 接受代码、Q3 保留 timeout 并有两次消费尝试、候选与评审角色分列。
- 核对场景展开和真实 SSE 更新后的页面滚动保持；回答在点击前不请求 artifacts；随后按按钮读取固定回答、文件及分类用量。
- 1280／390、dark／light 截图和横向溢出检查；批次名 HTML 转义；离开项目页后原 SSE 全部关闭。
- 输出 API details、attempts、artifacts、usage，交 inner 对真实 SQLite 独立对账。
- 只记录外部静态资源失败，不用它冒充业务 JS 失败；所有实际 Runtime 异常与业务弹窗都会失败。

已运行 Python 编译检查及 `--help`，并将草案内 56 条实际展开的页面 JavaScript 表达式交给本机 Node `vm.Script` 做语法解析，全部通过。尚未接上 HTTP／inner 握手，不能宣称本草案的完整浏览器链路已通过。

### 最小 inner 接线

改动建议限定 `deploy/v3/verify_project_scenarios.py` 的测试模式，主会话拥有实现：

1. 保留现有 `main.init_db()`、AccountRuntime、Scheduler、QuotaGuard、ProjectIterationManager 与 `start_run` 合成替身注入。
2. 在所有对象 patch 完成后，启动 `uvicorn.Server(uvicorn.Config(main.app, host='0.0.0.0', port=8000, lifespan='off', log_level='warning', timeout_graceful_shutdown=2))` 的 daemon 线程。必须 `lifespan='off'`：该进程已初始化真实对象，重复执行产品 lifespan 会覆盖它们。
3. 浏览器模式不调用当前约第 130 行的 `manager.create_batch()`／`transition()`。等待真实 API 产生第一条批次，记住其 ID，然后沿现有 `manager.tick()` 循环推进。创建前仍可 tick，但无需伪造任何业务表行。
4. 原机制循环完成时先保存机制证据，不立即 finally 清理；继续保留 HTTP 服务、manager 与文件，等待浏览器 done／失败或截止。否则页面读取回答和截图时数据会提前消失。
5. 浏览器返回的快照保存在本次共享 `/verify/scenario-browser.json`；inner 只读自己 `data/scenario.sqlite` 对账实际任务 ID、状态、attempt、Run 角色、评审作业、代码接受数及使用量来源，不能用回传的 passed 字符串代替数据库验证。
6. 所有浏览器退出路径最后关闭 SSE／Chrome，inner 再令 `server.should_exit=True` 并有界 join，随后沿原 finally 清理本次精确标签资源。

必要的只读数据库对账例子（字段均来自当前定义）：

```sql
SELECT t.id,t.task_key,t.status,t.attempt_count,t.accepted_checkpoint_digest
FROM project_scenario_tasks t
JOIN project_scenario_instances s ON s.id=t.scenario_instance_id
JOIN project_instances i ON i.id=s.instance_id
WHERE i.batch_id=?;

SELECT e.task_id,e.run_id,e.role,e.ended_at,r.status
FROM project_task_executions e JOIN runs r ON r.id=e.run_id;

SELECT task_id,attempt_no,reason,consumed_at,ended_at,result
FROM project_task_attempts ORDER BY task_id,attempt_no;
```

API 对账使用返回的 ID 联合定位，不能依赖某个临时数据库总是从 ID 1 开始。

### 最小 outer 接线

建议为 `run_local_verification.py` 新增 `--scenario-browser`（本研究不修改该产品测试入口）：

1. 仅允许与 `--project-scenarios-only` 组合。outer 生成一个本次随机的内部 token，传入 runner 环境 `V3_INTERNAL_TOKEN`，不能打印或放进 Chrome 参数。
2. runner 额外环境 `WEBUI_DIR=/source/webui`，复用现有 `/source` 只读挂载；只给测试 HTTP 端口发布 `127.0.0.1` 的随机宿主端口，例如 Docker SDK `ports={'8000/tcp': ('127.0.0.1', None)}`，reload 后读取真实分配端口。
3. 等 inner 的只读 ready 文件（或实际 `/api/project-catalog` 就绪）再启动本机草案；不要在 `runner.wait()` 阻塞后才启动浏览器。
4. 直接调用 async 草案函数或在独立子进程使用下面 CLI，等待它完成，再收取 runner 退出与原机制证据。Chrome 生命周期和随机数据根必须在原 finally 中精确收口。
5. 浏览器证据目录放在本次 evidence-dir 下面；如用 CLI，将 token 写入本次私有 0600 文件，通过 `--service-token-file` 读取，避免 shell 参数和日志暴露。

接线后的预期入口（当前尚未实现该 flag，不能直接当作现有命令）：

```bash
PYTHONPATH=orchestrator .deploy/project-iteration-repairs/venv/bin/python \
  deploy/v3/run_local_verification.py \
  --manifest .deploy/project-scenario-workflows/manifest.json \
  --project-scenarios-only --scenario-capacity 1 --scenario-browser \
  --evidence-dir .deploy/project-scenario-workflows/browser-capacity-1
```

当本次 inner 服务已经接好时，草案本身的现有可执行命令为：

```bash
PYTHONDONTWRITEBYTECODE=1 .deploy/project-iteration-repairs/venv/bin/python \
  .trellis/tasks/10-21-project-scenario-workflows/research/verify_scenario_browser.py \
  --base http://127.0.0.1:<本次随机端口> \
  --service-token-file <本次私有token文件> \
  --evidence-dir <本次浏览器证据目录> --capacity 1 --timeout 600
```

### catalog 503 的故障注入

不需要新增产品 HTTP endpoint，也不应修改或删除已冻结发布、DB、成果文件。

草案可接受 `catalog_fault_request` 文件路径。任务真实 completed 后，浏览器写入本次共享文件：

```json
{"schema":1,"action":"disable_current_catalog","batch_id":123}
```

inner 的测试等待循环见到请求、核对当前真实 batch_id 后，只在测试进程临时把 `manager.library` 置为 None，并保存／finally 恢复原引用。这正好触发 `main._project_manager(require_catalog=True)` 的现有 503 分支，历史接口仍使用已绑定 manager 和 `_libraries` 冻结发布缓存。

浏览器随后实际请求 catalog 503、重新进入项目页，检查创建表单被禁用、历史批次和实例／用量仍为 200、页面仍可打开实例。草案没有提供该共享文件时，会把此项写入 not_run，不能把未注入的情形说成已覆盖。

## Files Found

- `deploy/v3/verify_stack.py:53`：当前 Compose／网关与浏览器总入口，没有新场景 flag。
- `deploy/v3/verify_project_browser.py:14`：旧项目 UI 夹具，含人工注入业务结果，不能复用为新执行成绩。
- `deploy/v3/verify_browser.py:20`：Chrome 私有进程、CDP、RPC、页面等待和精确进程组清理范例。
- `deploy/v3/run_local_verification.py:74`：runner 启动及共享数据挂载；需在等待前接宿主 Chrome。
- `deploy/v3/verify_project_scenarios.py:73`：当前真实新场景执行链；约第 130 行的自动建批次须在浏览器模式交给页面。
- `orchestrator/main.py:8036`：原内部 Bearer 鉴权；`main.py:10239` 为当前目录可用与历史读取门禁。
- `webui/app.js:114`：真实项目页加载；`app.js:208` 为创建请求；`app.js:432` 为新场景 DOM 与 SSE 重绘。
- `webui/index.html:69`：真实项目表单和预算字段。
- `images/v3/Dockerfile:33`：control 原静态文件与代码落点；源码挂载的来源边界应准确记录。

## Code Patterns

- 真实选择器为 `#project-batch-form`、`[data-project-action=start]`、`[data-project-instance]`、`details[data-scenario-id]`、`.project-scenario-task`、`[data-scenario-artifact]`、`[data-scenario-usage]`。
- nested 证据接口为 `/api/project-instances/{iid}/scenario-tasks/{tid}/{attempts,artifacts,file}`；旧顶层路径不能代替新任务接口。
- `paintScenarioInstance()` 使用场景 details open 和 host scroll；浏览器既检查 DOM 的 open，也检查真正页面 scrollY，不用不可滚动容器恒为零冒充滚动验证。
- 项目流为 `/api/project-iterations-stream`；离开页签必须让 `state.projectEventSource === null`，已有 source 对象也应 CLOSED。
- Uvicorn 的 off lifespan 与 timeout_graceful_shutdown 已从本机安装源码核对，可复用已初始化对象，不改产品生命周期。

## External References

没有访问外部资料；CDP 调用方式沿用现有项目验证器，依赖 API 从本机安装源码核对。Chrome 版本为此次本机命令实际输出。

## Related Specs

- `.trellis/spec/vibecoding-bench/frontend/index.md`、`quality-guidelines.md`：零构建、真实浏览器、明暗主题、转义与 SSE 生命周期。
- `.trellis/spec/vibecoding-bench/backend/project-iterations.md`：页面／API／DB 同源及不可用目录的历史边界。
- 当前 task `design.md:160`、`implement.md` 阶段 5／6：场景展示、独立结果、完整尝试成本与跨层验证。

## Caveats / Not Found

- 草案仅位于本任务 research；没有修改产品、规范、验证入口或 Git 状态。
- Python 语法、CLI help 和 56 条页面 JavaScript 解析已通过；完整 Chrome 场景验证尚未运行，等待主会话接 inner／outer。
- 直接 main UI 的证据不覆盖统一网关 Cookie／管理桥，后者仍由原 verify_stack 浏览器链路独立验证。
- 6 任务为隔离机制夹具，不是正式三项目的 13 场景／20 任务，更不是模型质量成绩。
- catalog 503 仅通过测试进程临时 current library 故障注入，不新增产品端点、不写历史结果。
