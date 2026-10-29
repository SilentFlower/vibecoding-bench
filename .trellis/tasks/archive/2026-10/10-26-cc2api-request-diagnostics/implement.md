# cc2api 请求级排障观测实施计划

## 范围与阶段

Brief 已确认，任务已启动并通过 `trellis-route(target=implement)` 进入 inline 实现，已加载 `trellis-before-dev`。实现只修改 cc2api 后端与相关规范/测试，不修改线上配置或部署。

## 实施顺序

- [x] 定义请求、尝试、结果、错误阶段和白名单摘要模型；明确 null、部分用量与一次性终态。
- [x] 增加独立诊断 store、SQLite/PostgreSQL 幂等迁移、有界后台写入、八天保留与分页详情查询。
- [x] 在 messages 入口和实际发送边界接入关联 ID、画像、最终参数及匿名 session/thread 信息，覆盖本地 early return、缓存和模拟。
- [x] 贯通现有 PreparedRequest 的尝试 UUID 与 sender 证据；添加下游关联响应头，保留上游已有 ID。
- [x] 复用现有有界响应解析，记录 stop_reason、模型、token 和完整/中断状态，覆盖 EOF/error/Drop 及签名/401 重试。
- [x] 接入管理员查询 API，补充运维字段说明、留存与故障信号。
- [x] 完成定向回归、双数据库验证与完整 Rust 检查，通过 Full Check-All，并更新项目规范。
- [x] 按确认的 Git 计划提交并推送业务变更，任务进度 helper 已写入 completed 并完成 Close。

## 重点文件

- `cc2api/src/service/gateway.rs`、`usage.rs`、`runtime_transport.rs`：请求/发送/响应生命周期。
- `cc2api/src/service/telemetry.rs`：已定义的安全用量/结果模型；不借机开启或扩张遥测。
- `cc2api/src/model/`、`store/`、`store/db.rs`：新增诊断模型、存储及迁移。
- `cc2api/src/handler/router.rs`、`main.rs`：查询装配、管理员鉴权和写入器生命周期。
- `cc2api/tests/`：本地真实传输、存储与路由回归。

## 验证计划

1. 本地模拟上游覆盖 R1～R3：单次 JSON/SSE、分块、压缩、401→恢复/失败、签名重试/换号、本地拒绝、模拟/缓存命中、取消、流中错误；各请求和尝试唯一，费用次数不变。
2. R2/R5：交错 280/293 请求、同账号不同会话及 TTL 重映射，诊断匹配实际发送值且不改变缓存、thread、headers/body 和 session 行为。
3. R4：SQLite 独立 reader、重开连接、幂等迁移、分页筛选、八天边界；显式启动本地 PostgreSQL 运行等价 store/API 测试，不能用 ignored 当作通过。
4. R4/R5：队列饱和、写入失败、重复终结、超限和坏压缩；响应行为保持，失败信号可观察。
5. R5：合成凭据、Cookie、正文、工具参数及任意错误文本不出现在诊断表、API 或新增日志；未鉴权管理查询被拒绝。
6. 执行 `cargo fmt --check`、`cargo test --locked`；若共享协议处理被触及，执行 `cargo test cch`。本轮没有前端改动；范围扩大到前端时先更新规划并补 `npm run build`。

## 实现记录

- 已接入请求/尝试生命周期、最终参数与匿名 session/thread、重试原因和兼容响应头；管理 API 与运维文档已补齐。
- 采集健康包含丢弃事件、写入/清理失败和响应观察失败，均为进程内计数。解析缺口保留 partial 和受控错误类型。
- PostgreSQL 实测发现 SQLx Any 0.7 的 NULL 绑定使用 i32，会让缓存语句在可空字段从无值切换到实值时出现参数类型漂移。诊断 SQL 改为固定类型绑定并由 NULLIF 还原 NULL；等价双库契约覆盖先开始、后终结、重复写入。
- 本地 lib 回归首轮为 606 passed / 1 ignored；已在独立 PostgreSQL 实际执行 ignored 存储测试。最终全量回归与 Check-All 结果记录于 research/validation.md。

## 回滚与交付门禁

- 所有本地测试使用合成数据和本地上游；不刷新生产凭据，不发送线上探测。
- 新表只追加；回滚旧二进制后保留表，不删除既有统计。
- Check-All 完成后遵循其处置与 Post-Check Stop Gate；通过后更新规范，提交、推送和部署分别服从适用授权。
