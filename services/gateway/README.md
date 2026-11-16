# flower2api 网关

flower2api 的 Rust 服务，负责 API 鉴权、账号池、请求调度与转发、用量记录和管理接口。Vue 管理后台位于 [apps/web](../../apps/web)，由网关提供生产静态资源。

## 来源

该目录整合自 `SilentFlower/cc2api`，导入提交为 `7cbf3e354e9e5570b4e323362c18e5133d913a3e`，沿原 v3 锁定版本继续维护。详细记录见 [组件来源](../../docs/migrations/flower2api-sources.json)。

导入时的 CC-Bridge 介绍和贡献者信息保存在 [上游说明](README.upstream.md)。第三方许可分别位于 [craftls](craftls/LICENSE)、[hyper](vendor/hyper-1.9.0/LICENSE) 和 [reqwest](vendor/reqwest-0.12.4/LICENSE-APACHE) 等源码目录。

## 目录导航

| 路径 | 内容 |
| --- | --- |
| `src/main.rs`、`src/lib.rs` | 服务入口和库模块 |
| `src/handler/` | HTTP 路由与管理接口 |
| `src/service/` | 请求转发、账号调度和运行时接入 |
| `src/store/` | 配置、账号、请求及数据库迁移 |
| `src/bin/` | 账号发送器等独立入口 |
| `craftls/`、`vendor/` | 随仓库维护的依赖实现 |
| `scripts/` | 本地开发和构建工具 |

## 本地开发

从本仓库获取 flower2api 源码，随后在该目录执行：

```bash
cp .env.example .env
# 按本机环境设置独立数据库、监听地址及管理密码。
./scripts/dev.sh
```

脚本读取 `../../apps/web`，准备前端产物后启动 Rust 服务。配置项见 [.env.example](.env.example)，默认端口为 `5674`。Rust 构建读取同仓 `Cargo.lock`、`craftls` 和 `vendor`。

单独构建和验证，从仓库根执行：

```bash
npm --prefix apps/web ci
npm --prefix apps/web run build
cd services/gateway
cargo fmt --check
cargo test --locked
cargo build --locked --release --bins
```

内部 crate 和可执行文件保留 `claude-code-gateway`／`account-sender` 名称，以延续现有脚本和升级合同。

## 平台部署与升级

flower2api 通过 [联合构建入口](../../deploy/flower2api/README.md) 生成同批 control／account 两类镜像。网关与编排服务按原部署配置协作。正式发行、签名目录、数据库迁移和现有实例原地升级统一遵循 [系统更新 SOP](../../deploy/flower2api/SYSTEM-UPDATES.md)。

目录整合和旧路径映射见 [单仓说明](../../docs/migrations/flower2api-layout.md)。

## 会话策略封禁

管理后台“网关 → 会话封禁”展示策略拒答触发的封禁、到期及提前解除记录，提供状态筛选、匿名会话搜索、分页和关联请求入口。管理员可在确认后提前解除单条封禁。

“系统设置 → 会话与调度 → 会话策略封禁”提供自动封禁开关和时长。默认开启，时长默认 1440 分钟（24 小时）；修改仅影响新封禁，重复拦截保持原到期时间。列表顶部的“封禁设置”可直达该分区。

封禁以访问令牌与改写前真实会话共同隔离。有效封禁的消息及携带相同会话的 token 计数请求本地返回 HTTP 400，错误码为 `session_policy_blocked`，响应提供到期时间。自然到期或提前解除后恢复正常处理。记录持久保存，原始会话标识和正文保持私有。

| 设置键 | 默认值 | 作用 |
| --- | --- | --- |
| `session_policy_block_enabled` | `true` | 启用自动登记和本地拦截；关闭时保留历史 |
| `session_policy_block_duration_minutes` | `1440` | 新封禁持续的正整数分钟数 |

封禁状态查询失败时请求本地返回 503。首次发现拒答需要上游响应，标记前已提交的请求沿原生命周期结束。
