# 实施计划

## 1. 发布门禁

- [x] 确认 cc2api 协议子任务和 vibecoding-bench 运行时子任务均通过 Check-All。
- [x] 确认 cc2api 子模块提交、父仓 gitlink 和父仓提交已推送。
- [x] 等待两个 GitHub Actions 工作流成功，记录目标 SHA tag 与镜像 digest。

## 2. 生产预检与备份

- [x] 检查 cc2api / vibecoding-bench 健康、established 连接数和当前 image ID/tag。
- [x] 备份 cc2api SQLite，记录恢复命令和备份校验值。
- [x] 脱敏记录 profile/range、system-role、自定义设置、canonical env 版本分布。
- [x] 记录 vibecoding-bench WebUI 版本覆盖和账号 `allow_1m_models` 对比基线。

## 3. 升级 cc2api

- [x] 在低连接窗口 pull 正式镜像并 force-recreate gateway。
- [x] 验证根路径 200、容器 image ID、启动迁移和最近日志。
- [x] 查询 profile/range/canonical env/system-role，确认 2.1.257 与自定义值均正确。
- [x] 确认 `allow_1m_models` 未变化。

## 4. 升级 vibecoding-bench

- [x] 将 `VIBEBENCH_TAG` 锁定为本次成功 SHA，并将环境默认版本同步为 2.1.257。
- [x] pull 三镜像并 force-recreate orchestrator。
- [x] 验证首页/API、数据挂载、三镜像 tag 与 orchestrator 环境。
- [x] 启动一个安全验证 worker，确认实际 `claude --version` 为 2.1.257。

## 5. 集成观察与回滚准备

- [x] 检查版本拒绝、system-role 400、CCH/signature、migration 和 stream timeout 日志。
- [x] 若出现 Fable 5.1 no-response，确认日志为 0 chunk first-byte timeout 且含 request ID。
- [x] 核对旧 image ID/tag、DB 备份和回滚命令仍可用。
- [x] 将脱敏部署证据写入任务记录并执行发布 Check-All。

## 停止条件

- established 连接数高于低风险阈值。
- 任一目标镜像 digest 不可解析或三镜像 tag 不一致。
- DB 备份失败或恢复路径无法核对。
- 迁移覆盖自定义 settings、改变 `allow_1m_models` 或产生持续错误日志。
