# cc2api Backend Code-Spec Index

> 本层覆盖 `cc2api/` Rust 后端：Axum 路由、Gateway 热路径、账号调度、settings、数据库迁移、缓存和测试。协议画像细节见 `protocol/`，前端见 `frontend/`，部署见 `deploy/`。

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Service Architecture](./service-architecture.md) | Axum 入口、service/store/model 分层、Gateway 热路径和后台任务边界 | Filled |
| [Settings & Database](./settings-database.md) | settings 默认值、热刷新、SQLx Any、SQLite/Postgres 双栈迁移规则 | Filled |
| [Testing & Quality](./testing-quality.md) | Rust 格式、单测策略、网关回归、敏感数据边界和 review 清单 | Filled |

---

## Pre-Development Checklist

修改 `cc2api/` Rust 后端前必须：

1. 读取本层相关 guideline。
2. 搜索目标字段、setting key、路由名或函数名，确认是否已有同类实现。
3. 涉及 `/v1/messages`、Claude Code header/body、CCH、`cc_version`、bootstrap 或 telemetry 时，同时读取 [protocol](../protocol/index.md)。
4. 涉及管理页展示或设置项时，同时读取 [frontend](../frontend/index.md)。
5. 涉及镜像、远程 compose 或环境变量时，同时读取 [deploy](../deploy/index.md)。

## Quality Check

提交前至少运行：

```bash
cd cc2api
cargo fmt --check
cargo test
```

如果改到前端或嵌入资源，再运行：

```bash
cd cc2api/web
npm run build
```

---

**Language**: 中文撰写；Rust 类型名、setting key、header、SQL、命令和模型 ID 保留原文。
