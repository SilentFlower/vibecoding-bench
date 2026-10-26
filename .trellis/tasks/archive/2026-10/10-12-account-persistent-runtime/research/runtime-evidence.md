# 固定账号环境的规划证据

## 调研边界与工作区基线

- 本任务由用户明确要求“创建任务进行改造”，承接本会话已经讨论的固定环境方案。
- 创建前当前任务为空；Git 为 `main`。已有用户改动仅 `.trellis/spec/vibecoding-bench/deploy/official-protocol-capture.md`，后续不得覆盖或回退。
- 本次规划只读产品代码和规范，未启动真实账号请求，未修改产品实现或 cc2api 子模块。
- 本任务是一项需要共同验收的环境改造；登录、续聊、抓包和额度共享环境与执行归属契约，不能在其中某条入口仍使用破坏性旧清理时独立交付。

## 当前代码与约束

| 位置 | 已确认事实 | 改造影响 |
| --- | --- | --- |
| `orchestrator/main.py:1237`、`:1391` | 裸 SQLite，账号及运行历史存在幂等 schema 升级 | 新状态要兼容旧数据，不能重建数据库 |
| `orchestrator/main.py:2507` | hostname、MAC、LANG、内存等由账号名称派生 | 首次生成后固化，迁移不能因派生池变化静默变更身份 |
| `orchestrator/main.py:3309`、`:3546` | 每 run 创建 worker/sidecar，容器退出代表执行结束，cleanup 删除二者 | 固定容器需要独立执行句柄与终止/等待机制 |
| `orchestrator/main.py:3283` | 额度挂载与 source、identity、信号路径按 run 准备 | 固定挂载必须支持运行来源切换，保持只读控制边界 |
| `orchestrator/main.py:3627`、`:4385`、`:3763`、`:3998` | 续聊、登录、查询和刷新还有单独临时容器路径 | 必须统一适配，不能只改 `start_run` |
| `orchestrator/main.py:4422`、`:7591` | 重授权暂存凭据、取消可保留旧账号；成功提交后删除部分历史目录 | 暂存保护要保留，持久 HOME 不能被登录提交重置 |
| `orchestrator/main.py:5110`、`:5132` | session 查找和统计扫描 run 的旧 `.claude-home` 项目路径 | 共享 HOME 后要用显式主会话关联与执行偏移，保留旧布局读取 |
| `orchestrator/main.py:5316`、`:5635` | 默认同账号信号量为 2，普通执行进入后再检查账号并同步凭据 | 统一串行租约须覆盖其他入口，不能只把常量改成 1 |
| `orchestrator/main.py:6235` | 养号要求已绑定、已启用；只排除已有 active warmup | 新增对其他账号作业和排队工作的让路，保留现有认领及回调保护 |
| `orchestrator/main.py:6464` | 启动时额度恢复、旧登录/续聊/刷新容器清理先于后台调度 | 改为先收集证据、隔离旧执行、对账环境，再恢复调度 |
| `images/worker/entrypoint.sh:1535` 起 | 启动时写 machine-id、装 CA、校验/安装 CLI，task 模式使用固定 `/workspace` 和多个 `/tmp/claude-*` 文件 | 拆分环境准备与作业入口；临时状态、cwd、tmux 和钩子需按执行隔离 |
| `images/sidecar/start.sh:80`、`images/sidecar/recorder.py:18`、`:396` | flow 路径、完整记录、忽略域名和额度来源在 mitmdump 初始化时确定 | 不能通过修改容器环境变量冒充动态切换；必须实现显式上下文与确认机制 |
| `scripts/init-account.sh:70` 起 | legacy 引导独立临时容器，退出即删除，不走正式 sidecar | 不再把它描述成固定环境初始化入口；已有 profile 仍可导入 |

## 规范与回归依据

- `backend/database-guidelines.md:175` 起：绑定唯一性、owner -> profile 锁顺序、排队后再次同步、养号终态绑定保护。
- `backend/database-guidelines.md:498` 起：被动额度来源、身份、控制文件、原会话恢复与永久认证失败。
- `deploy/official-protocol-capture.md:112` 起：串行、120 秒间隔、异常冷却；`:138` 起：原始证据受限，页面脱敏。
- `deploy/image-build-push.md:445` 起：首轮权限引导不能吞题目，身份配置合并不能覆盖已有字段。
- `backend/quality-guidelines.md` 部分 P1 段落仍称没有测试，但实际已有 unittest，backend/index.md 与近期额度任务也记录回归。实现以当前测试及较新的专项契约为准，不删测试、不引入另一套测试框架。
- 当前自动化入口：`orchestrator/test_main.py`、`orchestrator/test_quota.py`、`orchestrator/test_worker_startup.py`、`images/sidecar/test_recorder.py`。

## 参考项目与取舍

- 本会话已只读调研 `dofastted/vm2api`，固定提交 `dc2513bff36dbc47880eeb42ae1540496799179f`。参考源码在 `/tmp/vm2api-architecture-review-20261012`，证据链接为该提交下的 `src/lib/vm/machine-spec.mjs`、`src/lib/vm/vm-runtime.mjs`、`docs/INFERENCE.md` 与 `docs/BUILD.md`。
- 借鉴账号环境与作业解耦、持久 HOME 和受控重建；不复制 patched CLI 推理桥、KVM 路径或发行 payload，不改 cc2api 数据面。
- 此前服务器只读诊断摘要为 `/tmp/vibebench-device-audit-20261012.md`，临时文件不是实现依赖。已确认可控身份曾保持一致，实际封禁原因仍未知。

## 实现前必须验证的技术细节

- 用当前目标 CLI 的实际行为验证新 cwd 的项目索引与旧 session 迁移；若需要兼容映射，必须保留原会话，不允许用新题重跑代替恢复。
- 固定 sidecar 的动态完整记录应包含原生 `.flow`、完整 HTTP、忽略域名规则及额度配置；切换确认、连接排空和异常撤销需要行为测试。
- Docker exec 的退出、PTY 和孤儿进程收口必须验证；容器一直运行，不能继续用 `container.wait()` 表示任务完成。

这些属于实施中的技术验证，不新增产品范围；验证失败应修正机制，不能削弱 PRD 的恢复、证据或生命周期要求。
