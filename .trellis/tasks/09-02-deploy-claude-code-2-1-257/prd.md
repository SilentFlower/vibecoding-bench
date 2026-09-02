# 发布并验证 Claude Code 2.1.257 升级

## Goal

在 cc2api 协议与 vibecoding-bench 运行时两个子任务均通过检查后，发布镜像并在
`us.flower-cli.com` 完成低风险迁移、数据核验和可回滚的线上验证。

## Requirements

- 发布前确认两个实现子任务状态完成、相关提交已推送，工作流构建的镜像可按 SHA
  精确定位。
- cc2api 与 vibecoding-bench 使用各自现有发布流程；不以本地临时镜像替代正式
  GHCR 构建。
- 部署前只读检查 established 连接、当前容器 image ID/tag、Compose 环境、WebUI
  运行时版本覆盖、DB settings 和账号 canonical env 分布。
- 对 cc2api SQLite 和关键 settings 创建可恢复备份，记录路径、时间和旧 image ID，
  不在任务文档保存凭据或账号信息。
- 低连接窗口分别 recreate cc2api gateway 与 vibecoding-bench orchestrator；worker
  和 sidecar 使用同一 `VIBEBENCH_TAG`。
- 迁移后确认 default profile/range、system-role 列表和账号 canonical env 为目标值，
  且管理员自定义模型仍存在。
- 部署前后比对账号 `allow_1m_models`，必须保持不变；本次不自动开放 Fable `[1m]`。
- 验证普通 run、抓包、OAuth/login 或 quota 中至少一个安全路径实际使用 2.1.257；不在
  生产环境使用真实敏感 prompt 做破坏性测试。
- 日志检查必须能区分 Fable 5.1 首字节超时与普通 idle timeout，不输出 token、Cookie、
  prompt、响应正文或账号邮箱。

## Acceptance Criteria

- [x] cc2api 和 vibecoding-bench 正式镜像均能按目标提交 SHA / digest 解析，构建成功。
- [x] 部署前备份、旧镜像、连接数和关键配置快照均已记录且不含敏感信息。
- [x] cc2api 根路径健康检查 200，容器运行新 image ID，DB profile/range/canonical env
      全部符合 2.1.257 迁移预期。
- [x] system-role 列表包含 `claude-fable-5-1` 且保留既有自定义模型；
      `allow_1m_models` 与部署前完全一致。
- [x] vibecoding-bench 首页/API 健康，orchestrator 环境默认版本为 2.1.257，三镜像使用
      同一 tag；新 worker 的 `claude --version` 为 2.1.257。
- [x] 最近日志无新增 panic、迁移失败、版本拒绝或 system-role 本地 400；首字节卡死若
      再现，日志包含 request ID 和 0 chunk 原因。
- [x] 回滚命令、旧 tag/image ID 和 DB 恢复路径经只读核对可用。

## Out of Scope

- 不删除 Docker volume、不清空账号、不修改代理或 new-api 渠道配置。
- 不调整 Fable `[1m]` allowlist，不以线上实验推断未确认的计费能力。
- 不保证 Anthropic Fable 5.1 上游可用性；只验证本地诊断和转发行为。
