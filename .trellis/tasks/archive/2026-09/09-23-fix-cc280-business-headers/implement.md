# 实施与验证

1. 扩展 version_profile、rewriter 的版本化端点、头部白名单、排序与 Sonnet 可选 beta；增加协议正反例。
2. vendor 固定 hyper/reqwest 源码及小补丁，业务 forwarding 启用请求级大小写；补原始 TCP 回归，覆盖重定向和 HTTP 代理。
3. cargo fmt --check、cargo test、cargo test cch；复跑既有脱敏审计；内联 Check-All，更新协议规范与验证记录。

执行依据：用户本轮明确要求四项修复；不扩展到遥测、访问策略或发布。

## 实施结果

- `version_profile.rs`：新增 280 端点枚举、版本化 MCP capabilities 及模型级客户端可选 beta；只为 280 Sonnet 4.5 声明 message-threads 可选。
- `rewriter.rs`：端点白名单、UA/beta 归一化、抓包大小写/排序已实现；Frame 版本取所选画像，会话与耗时透传。
- `gateway.rs`：业务转发和 count_tokens 显式传递 casing，event_logging/eval 不启用；加入发送原始字节回归。
- `vendor/`：原始 hyper 1.9.0 与 reqwest 0.12.4 共约 2 MiB，仅修改 3 个源码文件；许可证、归档摘要、可复核补丁齐全。Cargo 固定版本，Docker 同步复制本地依赖。
- 协议规范已同步；正文、CCH 算法、访问策略和遥测实现未改。

## 验证证据（2026-09-23）

| 验证 | 结果 |
| --- | --- |
| `cargo fmt --check` | 通过 |
| `cargo test --locked --offline` | 592 项通过，0 失败；535 单测、28 调度、13 时间戳、6 网关重试、4 TCP 大小写、6 Redis URL |
| `cargo test cch --locked --offline` | 23 项通过 |
| 本地/正式已有抓包复跑 | messages 67、Frame 4、MCP 35、模型选择 7、组织资源 93、mcp_servers 7；合计 213 条在核对范围内无 missing/added/changed |
| vendor 与发布归档差异、补丁反向 dry-run | 通过；只有 README 声明的 3 个源文件有差异 |
| 两仓 `git diff --check` | 通过 |

抓包验证调用本轮实际编译的 Rust 库；对身份转换字段（Authorization、OS、架构、组织 ID）及传输自动头不作相等断言。实际大小写、顺序和 Content-Length 另由 TCP 测试确认。脱敏结果保留在 `/tmp/cc280-audit/after-fix-business.jsonl`，未提交原始抓包。

全量测试日志 `/tmp/cc280-full-test.log`，CCH 日志 `/tmp/cc280-cch-test.log`。构建时 vendored reqwest 的旧 cfg/dead_code 警告及既有 Redis/SQLx 未来兼容提示不影响通过；未扩大到依赖升级。

最终显式导入/注释整理后，格式检查、网关实际发送测试 1 项（覆盖 6 个路径）及 TCP 集成测试 4 项再次通过；日志为 `/tmp/cc280-final-gateway-test.log` 与 `/tmp/cc280-final-wire-test.log`。其余语义未变，复用此前全量结果。

## 内联检查结论

检查画像为 interactive / requested=auto / effective=full / confidence=high：涉及协议字段与 HTTP 发送链。规划实现、API/数据流假设、规范与完整性均通过；无剩余 CHK/FBK。已检查默认请求隔离、旧版本 UA/beta、Fast/1M、safeguard、代理/重定向、敏感头删除及构建分发入口。

实现与验证已完成，业务代码、协议规范及子模块指针已提交并推送；任务完成记录随本次记录提交同步，尚未部署。线上真实账号请求效果属于后续发布验证，本轮没有调用上游业务接口。

推送前的暂存检查另核验了第三方原件：两个 `.patch` 的空白上下文通过完整差异重建和反向 dry-run；reqwest 的 `CHANGELOG.md`、`LICENSE-MIT` 与原始归档逐字节一致。仅这四个文件保留上游或补丁格式要求的空白，其余暂存内容通过 `git diff --cached --check`。
