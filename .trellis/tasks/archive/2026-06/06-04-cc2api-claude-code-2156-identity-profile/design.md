# cc2api Claude Code 2.1.156 设备与运行身份画像优化设计

## Technical Design

### Profile 分层

设计上拆成三层：

- `DeviceProfile`：长期稳定，绑定账号。包含 platform、arch、node/runtime、terminal 家族、package manager、device id、build/version、account/org 标识。
- `RunProfile`：一次 Claude Code 运行。包含 run id、cwd、shell、started_at、process seed、session seed、telemetry session。
- `RequestProfile`：单次请求。包含 request id、message session id、client request id、first byte timing、retry attempt。

现有 `canonical_env`、`canonical_prompt_env`、`canonical_process` 可以先保持存储结构不变，在服务层通过 helper 派生 run/request 字段，避免大规模 DB migration。

### 字段一致性

- platform 为 linux 时，prompt OS、linux distro、kernel、working dir、shell、Stainless OS 必须一致。
- platform 为 darwin 时，terminal、shell、OS version、home path、arch 必须一致。
- platform 为 win32 时，prompt shell 的 Unix path 说明、working dir、Stainless OS 和 path rewrite 必须一致。
- GrowthBook 的 `platform`、`appVersion`、`deviceID`、`accountUUID` 使用同一 profile。
- telemetry `env` 使用 `build_full_env_json` 的完整 schema，但字段来源要集中。

### Process 曲线

用账号级 process seed + run started_at 生成可重复但非固定的曲线：

- uptime 单调递增。
- rss、heapTotal、heapUsed 在配置范围内小幅波动，不每次完全随机跳变。
- cpuUsage 随请求事件递增。
- constrainedMemory 与平台/容器画像相关。

### 兼容策略

- 旧账号读取失败时继续使用 `Default`，但提供补齐函数生成缺失字段。
- 不自动覆盖用户手动配置的 `canonical_env`。
- 新增管理接口或更新接口可触发 identity profile regenerate。

## Rollout / Rollback

- 第一阶段只新增 profile helper 和测试，不改变 DB schema。
- 第二阶段把 telemetry、rewriter、oauth header 都改为读取统一 helper。
- 如发现线上账号画像异常，可回退到现有 `canonical_env` 直接读取逻辑。
