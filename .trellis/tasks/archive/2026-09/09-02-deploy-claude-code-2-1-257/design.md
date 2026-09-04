# 技术设计

## 发布顺序

```text
两个实现子任务 Check-All 通过
  -> 推送 cc2api 子模块与父仓提交
  -> 等待/核验 GHCR 镜像
  -> 生产只读预检与备份
  -> 低连接窗口升级 cc2api
  -> 验证 DB/settings/日志
  -> 升级 vibecoding-bench 三镜像
  -> 新 worker 运行版本验证
  -> 集成观察与回滚证据确认
```

cc2api 先升级，使 2.1.257 worker 开始发请求前网关已经接受新版本和 Fable 5.1；
vibecoding-bench 随后升级，减少版本拒绝窗口。

## 发布入口

- cc2api：使用 `cc2api/.github/workflows/docker.yml` 生成
  `ghcr.io/silentflower/claude-code-gateway`，远程路径和 Compose 以现有部署配置为准。
- vibecoding-bench：使用 `.github/workflows/docker-publish.yml` 生成 orchestrator、worker、
  sidecar 的 `latest` 与 7 位 SHA tag，生产锁定同一 SHA tag。
- 远程主机使用用户提供的现有 SSH 权限，但密码不写入命令历史、任务文档或日志。

## 预检与备份

- 检查两个服务端口的 established 连接；高连接时停止 recreate 并等待低位。
- 记录当前容器 image ID、Compose service、环境中的版本/tag 和健康状态。
- 备份 cc2api SQLite 数据库，并只读导出 settings key/value 的脱敏快照和版本分布。
- 记录 vibecoding-bench SQLite 中 WebUI `claude_code_version` 覆盖值；如果仍显式为
  2.1.220，发布时按产品目标更新为 2.1.257或清空回退，但操作前必须明确记录旧值。
- 记录所有账号 `allow_1m_models` 的值摘要，部署后逐行或按 hash 比对不变。

## 验证与观察

- cc2api：容器、HTTP、profile/range、canonical env、system-role、自定义设置、日志。
- vibecoding-bench：容器、首页/API、三镜像 tag、orchestrator 环境、新 worker
  `claude --version`。
- Fable 5.1：优先使用无敏感内容的最小请求或自然流量观察，不伪造 `[1m]` beta。
- no-response：若上游复现，只确认日志阶段、request ID 和 chunk 数，不以增加 timeout
  或 keepalive 作为现场修复。

## 回滚

- 联合回滚必须先回滚 vibecoding-bench，再回滚 cc2api。旧 bench worker 镜像内置
  Claude Code 2.1.220，旧 cc2api profile 允许到 2.1.220；先把 WebUI 运行时版本覆盖
  固定为 2.1.220，可避免旧网关拒绝 2.1.257 worker。
- vibecoding-bench：确认无活动 run 后停止 orchestrator，先备份当前 DB 和配置，再恢复
  旧 `VIBEBENCH_TAG` / Compose / WebUI / DB，将页面版本覆盖固定为 2.1.220；验证旧
  配置和 worker 版本后保持停止，等待网关回滚完成再启动。
- cc2api：停止 gateway 后先备份当前 DB，再切回旧 image ID/tag、恢复数据库备份并
  force-recreate；确认旧 profile/range 和根路径健康。
- 不允许单独先回滚 cc2api；除非已经确认所有新 worker 的生效版本不高于 2.1.220。
  联合回滚期间 orchestrator 保持停止，避免调度任务落在网关切换窗口。
- 任何回滚都不删除 volume；失败证据和备份路径保留到父任务验收完成。
