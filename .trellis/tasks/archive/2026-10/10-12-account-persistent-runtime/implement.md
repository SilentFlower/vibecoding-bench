# 实施计划

## 实施顺序

本任务保持统一交付，以下是内部实施步骤，不能在某条旧入口仍会删除固定环境时宣布改造完成。

### 1. 前置行为验证与持久化基础（R1、R2、R9）

- [ ] 阅读当前 backend/deploy/frontend 规范、实体/DTO、Runner、LoginSession/ContinueSession 定义及相关测试，核对实际安装 CLI 的行为。
- [ ] 验证 Docker exec 的退出/PTY/子进程行为，以及目标 CLI 的 cwd/session 索引与旧会话恢复；固化可执行夹具，避免根据猜测写新路径。
- [ ] 定义拟新增环境注册与执行关联字段，幂等 schema 升级，历史运行新字段允许为空；为 ID/配置冲突给出明确错误。
- [ ] 建立每账号环境目录、固化身份与原资料迁移清单，支持草稿登录环境绑定正式账号，不覆盖已有 userID/machineID。

### 2. 环境和作业进程（R2、R3、R4）

- [ ] worker 增加持久运行模式，拆分基础准备和任务作业入口；Dockerfile 明确 COPY 新文件，使用现有 tini 管理容器。
- [ ] CLI 安装按版本复用；job env、cwd、tmux、临时标记、完成钩子、状态及 transcript 按 source/代次隔离。
- [ ] 环境管理提供准备/健康/启动/空闲停止/对账；Runner 启动、等待和停止改用执行句柄，正常任务结束不 remove 环境。
- [ ] 建立所有正式入口共用的账号串行租约，保证取消/终态代次检查，收口失败隔离账号环境并保留数据。
- [ ] 按 run 关联主会话和项目路径，改造统计、文件、transcript、会话查找与历史布局兼容，不扫描整个 HOME 累加。

### 3. sidecar、额度与抓包（R6、R7）

- [ ] 实现账号 sidecar 执行上下文原子发布、验证与确认，覆盖输出目录、source/identity、凭据和额度信号路径。
- [ ] request 开始固定所属上下文，response 与晚到数据只写原来源；缺失/损坏/过代配置阻止正式模型请求。
- [ ] 保留现有被动响应头解析、即时请求门禁、恢复认领和永久认证错误；挂载控制目录保持 worker RO，变更形状同步专项 spec。
- [ ] 抓包上下文同时控制完整 HTTP、`.flow`、索引和忽略域名选项，不能只切 JSONL 开关。
- [ ] 实现执行结束、连接收口、证据落盘和诊断撤销确认，覆盖停止/超时/异常；撤销失败不能继续放行普通作业。
- [ ] capture run、capture continue 和恢复共用全局串行、120 秒间隔及异常冷却，更新 SOP 的执行隔离含义并保留用户已有文档改动。

### 4. 调度及账号入口适配（R3、R4、R5、R8）

- [ ] 普通/批次/capture run 与 quota_wait 恢复适配租约和句柄；Compose 上限与批次 UI 反映同账号串行，不更改既有执行快照语义。
- [ ] 登录/重授权、ContinueManager 与 WS、手动额度查询、未绑定账号刷新全部复用环境；交互入口忙时明确冲突。
- [ ] 保留重新授权的暂存/取消保护，成功提交不删除持久 HOME/会话；绑定切换仍检查 active run、quota_wait、login 和 continue。
- [ ] 保留 cc2api 唯一刷新责任及 managed 401 同步，排队取得执行权后再次同步；修改 bench 凭据桥接时不修改 cc2api 子模块。
- [ ] 养号忙时顺延、低优先级让路，保留默认间隔、选题、绑定门槛、终态绑定校验及失败暂停策略。
- [ ] lifespan 先收集额度补证、严格隔离旧执行并对账，再启动后台调度；等待、已取消、停用和软删除工作不得复活。

### 5. 页面、交付和迁移说明（R4、R9）

- [ ] 账号列表增加必要环境提示，继续使用现有静态 WebUI 与中文错误；校验登录/续聊 PTY 和事件更新。
- [ ] 同步两个 Compose、`.env.example`、README、镜像构建文件及 legacy 初始化脚本说明，避免推荐另一套临时设备。
- [ ] 编写迁移/镜像重建/回滚操作说明：旧执行隔离、SQLite backup、凭据桥接、历史目录保留和新旧镜像兼容组合。
- [ ] 保护规划前已有 `official-protocol-capture.md` 修改，不回退用户内容；只在当前实际变更依据下追加/更新相关契约。

### 6. 验证与质量检查（A1–A9）

- [ ] 新增有行为价值的回归：持久复用、旧身份迁移、草稿绑定、串行与养号让路、停止/重启竞态、主会话归属、抓包撤销、额度及凭据所有权。
- [ ] 使用脱敏 JSONL 和真实 shell 函数验证旧会话恢复、首轮题目提交和权限保持；避免只用字符串匹配验证业务逻辑。
- [ ] 运行后端与 sidecar 回归、语法检查、Compose config 和 `git diff --check`；记录命令和实际结果。
- [ ] 在隔离本地数据中执行 Docker 生命周期验证，确认第二次运行复用环境/安装、exec 完成不退出容器、子进程收口、空闲唤醒、镜像重建和目录权限。
- [ ] 按项目 SOP 留存真实 Claude 首轮/续聊与正式抓包验证证据；若环境/账号条件不足，明确未执行项，不用 mock 宣称官方协议或实机验收通过。
- [ ] 进入 `trellis-route(target=check)` 的统一质量检查，修复并复核；同步实际 spec、实现记录及验证结果，再按项目流程进入提交评审。

## 验证命令

在安装当前 `orchestrator/requirements.txt` 的隔离 Python 环境中执行现有测试；不引入新的测试框架。新增脚本和模块按实际文件名单加入语法检查。

```bash
python3 -m unittest discover -s orchestrator -p 'test_*.py'
python3 -m unittest discover -s images/sidecar -p 'test_*.py'
python3 -m py_compile orchestrator/main.py orchestrator/quota_protocol.py images/sidecar/recorder.py images/sidecar/quota_protocol.py
bash -n images/worker/entrypoint.sh
bash -n images/sidecar/start.sh
bash -n scripts/init-account.sh
node --check webui/app.js
HOST_BENCH_DATA=/tmp/vibebench-runtime-config/data docker compose -f docker-compose.yml config --quiet
HOST_BENCH_DATA=/tmp/vibebench-runtime-config/data docker compose -f docker-compose.remote.yml config --quiet
git diff --check
```

Docker 生命周期与真实账号验证属于行为验收，按实施时可用环境编写精确命令并保存结果，不在规划阶段执行。

## 风险文件与回滚点

| 变更区域 | 重点风险 | 回退条件 |
| --- | --- | --- |
| `orchestrator/main.py` | schema、统一租约、旧 cleanup、等待/终态与恢复竞态 | 保留旧布局读取；停止调度并确认无旧作业后才回退 |
| `images/worker/entrypoint.sh` 与拟新增 job 脚本 | `/workspace`、共享 `/tmp`、tmux/PTY、完成判断与 managed OAuth | 新旧 worker 与 orchestrator 必须兼容配套，不能只回退单个文件 |
| `images/sidecar/start.sh`、`recorder.py` | 上下文串包、完整记录残留、额度来源错配、连接未收口 | 失败先隔离账号；不能带着错误上下文继续普通请求 |
| `webui/`、Compose、README 和 specs | 并发展示不实、漏挂目录、旧初始化入口重建设备 | 端点请求兼容，目录与迁移手册随镜像一起验证 |
| `data/`（运行时，不入 Git） | 凭据、身份、旧会话、数据库与原始证据 | 迁移先备份和暂存；任何回退不删除 HOME/profile/workspace/flows |

本轮不改 cc2api 子模块、不自动执行线上部署。Brief 经确认后，先按阶段 1 验证关键技术行为和持久化基础，再推进共享契约。
