# 技术设计 — Claude 遥测收尾与原会话状态保留

## 边界与既有契约

- `Runner.start_run` 已把每个 run 的 `.claude-home` 挂载到 `/home/node/.claude`，其内容独立于容器删除；继续对话也使用原 run 的 HOME 与 Claude session。无需更换运行架构或数据库表。
- task 模式由 worker 内的 tmux 启动 Claude；continue 和 login 模式由 orchestrator 的 Docker exec 启动。login 模式入口直接 `exec tail -f /dev/null`，不能假设它具备 task 模式的 TERM trap。
- 官方客户端 2.1.293 对 SIGTERM、SIGINT、SIGHUP 注册原生退出处理，包括遥测刷新；旧队列按 Claude session 筛选。只读静态分析不是运行验证，受支持的实际版本仍需实现时核验。
- 完成判断保持稳定的最终 assistant JSONL 判定。worker 既有业务退出码为成功 0、超时 124、认证失败 42、额度等待 43；人工停止由 orchestrator 的既有优先级决定。
- managed OAuth 仍由 cc2api 持有 refresh token；本任务只沿用既有配置回写白名单与凭据新鲜度规则。

## 进程所有权与收尾

1. 在 worker 镜像内提供一个小型、无第三方依赖的进程生命周期辅助入口，统一供 task 启动命令、continue Docker exec 和 login Docker exec 使用。实际 Claude argv、用户、HOME、CA、权限模式和模型参数保持原契约。
2. 启动时先原子记录本次 Claude 的 PID、进程开始时间、运行归属和代次，再执行官方 CLI。记录按执行区分，不能覆盖仍活跃的旧记录；关闭容器时处理其中归属匹配的主 Claude，不碰认证查询、同步程序或其它辅助进程。不得用模糊的 `pkill claude`，也不从终端中输入 `/exit` 或新增模型提示。
3. 收尾核对本容器、本代次的进程记录与 `/proc` 中的身份；只有匹配时向该 Claude 发 SIGTERM，并等待实际退出。默认等待上限 15 秒，重复执行必须幂等。未启动、已经退出或记录过期单独返回脱敏结果；超时先记录强制收尾，再终止仍匹配的旧执行，最后由容器清理兜底。
4. task 模式的正常收尾、启动失败、EXIT/TERM/INT trap 均接入同一逻辑。主动终止前固定业务判断及当时是否自然退出，避免新出现的 `/tmp/claude-exited` 或信号退出码把 timeout、auth_failed、quota_wait、success 改成其它结果。
5. orchestrator 在停止容器前调用同一收尾入口，包括没有 task trap 的 login/continue worker。worker 的 Docker stop 时间预算至少 20 秒，覆盖内部 15 秒等待与持久化。worker 完成收尾和配置回写后才关闭 sidecar；原生退出期间仍保留现有代理路径。
6. 普通 cleanup 可沿用容器已不存在时的容错；额度恢复路径必须保留严格删除语义。删除失败时保留原 worker/sidecar ID 和代次，既不释放旧执行所有权，也不启动第二份执行。异步 WebSocket 的等待通过现有线程卸载方式执行。

## 状态保留与原生重试

- 去掉 task 初始化中的 `telemetry` 删除，以及 login commit 中对该目录的主动删除；`backups` 清理与会话归属规则独立处理。
- 额度恢复和继续对话保留原 `.claude-home` 下客户端的原生遥测状态，不新增跨 run 的队列回写白名单。原生新格式同样不主动删除、不自行解析或转换。
- 不把旧队列重命名为新 session，也不创建账号共享的遥测发送器。官方重试受 session、版本及重试次数限制，因此保存原文件只能保证状态保留，不能保证另一个新会话会发送它。
- 新 run 仍按既有 profile 初始化规则准备环境；本轮不扩大到全 HOME 持久化、共享缓存或用户数据迁移。

## 观测与安全

- 生命周期辅助入口仅输出本次归属、收尾结果、耗时及是否采用强制收尾；不记录 token、Cookie、Authorization、完整配置或事件内容。
- 不新增常驻遥测服务或主动 usage 请求。现有 `stats.jsonl` 的 request/response 阶段用于事后核查；没有响应的记录标记为未确认，HTTP 200 不解释为每条事件均已入库。
- 客户端内部刷新本身有短时等待预算；保留代理和进程等待不能提高其原生必达保证。额度拦截、网络故障和服务端拒绝仍可能导致事件未发送。

## 兼容、发布与回滚

- 需要 worker 与 orchestrator 配套，sidecar 协议和 cc2api 不变；没有数据库迁移，也不删除现有账号或工作目录。
- 辅助入口随 worker Dockerfile 复制并赋予正确执行权限，构建验证必须覆盖它。正式上线前按项目镜像与部署 SOP 准备版本一致的产物，本轮不自动部署。
- 回滚恢复原镜像即可，但旧镜像会再次短等待或删除目录，不能把保留了文件误认为旧版本能安全重试；不得为回滚删除保留的会话数据。

## 验证映射

- A1：真实初始化/提交逻辑执行于临时目录，预置多个 session 的待发送标记，验证保留与隔离。
- A2：可控进程替身在 TERM 后延迟写入收尾标记，证明等待完成后才关闭代理；覆盖无 PID、过期 PID、自然退出、重复关闭和忽略 TERM 的超时强制收尾。
- A3：真实 worker 收尾路径的业务结果矩阵，验证退出标记和 harness 信号不会改变原状态。
- A4：Docker 客户端替身验证正常/严格清理顺序、失败阻止恢复及继续对话代次保护，并检查异步关闭的线程卸载。
- A5：沿用 managed OAuth、profile 白名单与额度门禁的现有回归测试，核查无新增外部请求及敏感日志。
