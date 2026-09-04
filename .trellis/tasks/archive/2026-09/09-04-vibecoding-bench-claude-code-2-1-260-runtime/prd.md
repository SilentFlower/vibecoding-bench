# 升级并发布 vibecoding-bench Claude Code 2.1.260

## Goal

将 vibecoding-bench 全部新 worker 的默认 Claude Code 版本升级到 2.1.260，修复 run
没有持久化实际 CLI 版本导致继续对话回落到当前全局版本的问题，并完成 bench 三镜像
发布与生产部署，为用户后续抓包提供统一环境。

## Confirmed Facts

- 当前所有默认值为 2.1.257，分布在 worker Dockerfile/entrypoint、orchestrator、
  Compose、`.env.example`、WebUI、README 和测试。
- `runs` 表当前没有版本字段，只有抓包模型覆盖字段
  `capture_model_override`（`orchestrator/main.py:1323`）。
- `Runner.start_run()` 在 worker 真正启动时调用
  `effective_claude_code_version()`（`orchestrator/main.py:2471`）。
- `Runner.start_continue()` 再次调用当前全局有效版本
  （`orchestrator/main.py:2800`），没有复用原 run 的版本。
- 抓包创建只保存模型覆盖，不保存 CLI 版本（`orchestrator/main.py:6959`）；继续接口
  虽然读取完整 run 行，但其中没有可用版本快照（`orchestrator/main.py:7323`）。
- 用户明确 bench 不做隔离双版本，第一阶段全部默认和生产 worker 都切换到 2.1.260。

## Requirements

### 运行时默认值

- worker Dockerfile、entrypoint shell/Node fallback、orchestrator 默认值、普通/批量/
  抓包/login/quota/OAuth worker、两份 Compose、`.env.example`、WebUI 和 README 全部
  同步到 2.1.260。
- 保持 WebUI 覆盖 > `.env` > 代码默认的优先级；保持版本格式校验、不一致自动安装、
  安装失败即失败的现有行为。
- 不改变默认模型、effort、代理、抓包隔离和 OAuth 所有权。

### run 版本快照

- `runs` 新增 nullable `claude_code_version TEXT`，通过 `_ensure_column` 幂等兼容旧库。
- 普通、批量、养号和抓包 run 在创建数据库行时解析并保存当时的有效版本；排队期间
  全局设置变化不得改变已创建 run 的版本。
- scheduler/Runner 必须显式传递并使用 run 快照，不能在启动时无条件重读全局版本。
- 继续对话必须优先使用原 run 的版本快照；历史 run 字段为空时回退当前有效版本，并
  在成功解析后补写该历史 run，避免下一次继续再次漂移。
- 同一 task 再次运行产生新 run，新 run 使用再次运行时的当前版本，不继承旧 run。
- run 列表和详情通过现有返回结构暴露版本；抓包创建和抓包详情响应显式返回实际版本。

### 发布

- 完成代码检查和提交后发布 orchestrator、worker、sidecar 三镜像的同一 SHA tag 与
  `latest`，再按远程部署规范 pull 并 force recreate。
- 部署前记录旧镜像、数据库快照、WebUI 保存的版本覆盖值；部署后把生产页面覆盖和
  `.env` 默认确认到 2.1.260。
- 用生产环境验证新普通 run、新抓包 run 和抓包 run 的继续对话实际版本。

## Acceptance Criteria

- [ ] 无页面覆盖时所有新 worker 路径使用 2.1.260；页面保存其他合法版本后新 run 使用
      覆盖值，清空后恢复 2.1.260。
- [ ] 每个新 run 的 `claude_code_version` 在创建时非空，API 可读取该值。
- [ ] 以全局 2.1.260 创建抓包 run 后，把全局设置改成 2.1.257并关闭原 worker；点击
      继续仍启动 2.1.260。此后创建的新 run 使用 2.1.257。
- [ ] 普通、批量、养号和抓包入口均覆盖版本快照测试；排队后改全局版本不影响已创建
      run。
- [ ] 旧 SQLite 幂等补列成功；历史空快照 run 可以继续，并在首次回退后固定版本。
- [ ] `python3 -m unittest orchestrator.test_main`、两份 Compose config 校验、默认版本
      审计和 Check-All 通过。
- [ ] 三镜像发布成功且生产容器健康；生产 run/continue 实际版本验证通过。

## Out of Scope

- 不修改 cc2api 版本画像或允许范围。
- 不分析 2.1.260 wire 协议差异；由后续抓包任务负责。
- 不为历史 run 猜测原始版本；缺失快照采用明确的当前版本回退契约。
