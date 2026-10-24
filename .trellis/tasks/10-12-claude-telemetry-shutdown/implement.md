# 实施计划 — Claude 遥测收尾与原会话状态保留

## 实施前门禁

- [ ] 三件套收敛并完整展示由其派生的 Brief，等待当前任务的规划确认。
- [ ] 确认后 `task.py start`，通过 `trellis-route(target=implement)` 进入实现；读取实际命中的层规范及实体/会话定义后才编辑代码。
- [ ] 保留用户已有的 `official-protocol-capture.md` 修改，不把账号限制排查扩展成风控规避或账号固定容器实现。

## 有序执行

1. **进程生命周期基础（R2、R5）**：实现 worker 内辅助入口及最小脱敏结果；核验 PID、开始时间、归属、代次和超时。同步 Dockerfile，使用临时目录与可控进程替身验证正常、强制、过期和重复收尾。
2. **task 收尾（R2、R3）**：接入 tmux 启动、启动失败及 EXIT/TERM/INT 清理。先固定原业务结果，再收尾 Claude，最后写回允许配置并结束 tmux；覆盖 0/124/42/43、失败和人工停止的原判定。
3. **orchestrator 及交互收尾（R2、R3）**：Runner、LoginManager、ContinueManager 统一在 worker 停止前调用辅助入口；login/continue Docker exec 记录实际 Claude 的进程归属；sidecar 最后关闭。严格额度删除失败阻止恢复，异步等待使用线程卸载，验证旧代次不得影响新执行。
4. **原会话状态保留（R1、R4）**：移除两处遥测目录主动删除，核对原 run 初始化、额度恢复、继续对话及登录提交。仅保留原生状态，不添加跨会话合并、身份改写或自行代发。
5. **回归与交付（A1–A5）**：执行聚焦测试和下列本地验证，记录真实结果、强制收尾边界及未验证的客户端版本；通过统一质量检查，再完成规范更新和后续提交流程。

## 本地验证命令

```bash
bash -n images/worker/entrypoint.sh
python3 -m unittest discover -s orchestrator -p 'test_*.py'
python3 -m unittest discover -s images/sidecar -p 'test_*.py'
git diff --check
```

辅助入口的 Python 编译或 shell 语法检查随最终文件类型加入验证记录。镜像构建依照 `.trellis/spec/vibecoding-bench/deploy/image-build-push.md` 执行本地构建校验；生产推送与部署另行处理。测试不得使用真实账号凭据或发送上游模型请求。

## 风险文件与回滚点

- `images/worker/entrypoint.sh`：信号、幂等清理、结果优先级、tmux 时序及 profile 初始化。
- `images/worker/Dockerfile` 和新增生命周期辅助入口：镜像内可用性、执行权限与版本配套。
- `orchestrator/main.py`：普通/严格清理差异、continue 代次与锁、WebSocket 关闭、login commit、凭据白名单。
- 回滚不涉及数据库和数据删除；必须同时回退配套镜像，保留已有 HOME 文件。完成严格清理失败测试前不得认定额度恢复路径可交付。

## 完成证据

- 在任务验证记录中逐项回填 A1–A5 的真实测试结果；未执行项必须说明。
- 收尾结果仅证明官方客户端获得退出与发送机会；外部 HTTP 响应、事件入库和账号限制原因分开陈述。
- 当前为 planning，仅完成研究和规划；不得以文件已创建代替产品实现或验收通过。
