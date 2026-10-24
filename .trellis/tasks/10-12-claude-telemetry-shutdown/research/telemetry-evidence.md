# 遥测生命周期证据

## 范围与方法

2026-10-12 对服务器数据库、已有 run 产物及本地官方 Claude Code 2.1.293 安装文件进行只读检查；没有启动真实账号模型调用、修改服务或运行伪造遥测。动态发送结果来自已有 `stats.jsonl`，客户端内部行为来自只读静态分析，二者不能互相替代。

## 服务器已观察的发送

- `10-11` 九次运行共观察到 `/api/event_logging/v2/batch` 等遥测批次的 254 条请求阶段记录及 248 条响应阶段记录，响应均为 HTTP 200；六条只有请求的记录不能当作发送失败或成功。
- 本批次没有观察到旧格式 `telemetry` 目录；目录不存在不证明功能关闭或没有未发送事件，新版存储、短暂队列和原生策略均影响目录状态。
- 只记录上述聚合事实，不保存凭据、组织标识、完整事件内容或账号敏感配置。

## 官方客户端静态机制

- 原生退出管理注册 SIGTERM、SIGINT 和 SIGHUP，退出时执行相关 hook、持久化队列及分析/遥测刷新。因此不能把 `tmux kill-session` 简化为“客户端必然不刷新”；问题在于外层没有等待实际退出便结束容器或代理。
- 旧格式待发送文件位于 `.claude/telemetry/1p_failed_events.<session-id>.<process-id>.json`，虽然后缀为 `.json`，内容实际按 JSONL 处理。
- 启动重试筛选当前 Claude session 的队列；新版日志存储的重试同样按 session 筛选。将旧队列简单放到账号公共 HOME，不能保证一个不同 session 会替它发送。
- 失败导出会持久化并按原生退避重试，重试上限及丢弃策略仍由官方客户端决定。内部分析刷新有约 500 ms 的等待预算，额外退出阶段还有自身等待；外层等待 15 秒不意味着事件必达。
- 本地静态分析针对实际安装的 2.1.293；服务器 `10-8` 使用 2.1.280，后续实现应核验支持版本，不能把一个版本的内部符号当作稳定公开 API。

## 当前代码缺口

| 入口 | 证据锚点 | 缺口 |
| --- | --- | --- |
| task 初始化/恢复 | `images/worker/entrypoint.sh:1630` | 无条件删除 telemetry，包括原会话恢复 |
| task EXIT/TERM/INT 清理 | `images/worker/entrypoint.sh:914`、`:1603` | 只做配置与工作目录清理，没有等待 Claude 退出 |
| task 启动失败与完成 | `images/worker/entrypoint.sh:1739`、`:1899` | 终止 tmux 后直接结束，不等待客户端原生收尾 |
| 普通 run 清理 | `orchestrator/main.py:3546` | worker 只有五秒 stop 预算，未显式等待主 Claude |
| 额度恢复前清理 | `orchestrator/main.py:3295` | force 删除 worker/sidecar，绕过进程收尾；严格失败契约必须保留 |
| continue 暂停 | `orchestrator/main.py:4774` | force 删除；需保持原 ID、代次和阻止重复执行的语义 |
| login/continue 主进程 | `images/worker/entrypoint.sh:1581`，`orchestrator/main.py:7485`、`:8798` | login 模式仅 tail 空转；Docker exec 中的 Claude 没有 task trap |
| 登录提交 | `orchestrator/main.py:7665` | 主动删除 profile 遥测，且“所有历史队列会重放”的注释与按 session 筛选不符 |

## 可支持的结论

修复顺序、等待及删除行为有明确工程价值，不需要更换为账号固定容器。它减少本系统造成的中断和原会话数据丢失；不能证明缺陷造成账号限制，也不能保证服务端接受、逐事件入库或跨会话重试。
