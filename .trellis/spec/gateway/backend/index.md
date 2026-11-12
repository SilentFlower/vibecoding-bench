# 网关后端规范

## 适用范围

services/gateway/ 的 Rust/Axum、账号池、设置及存储。

## Guidelines Index

| 规范 | 说明 |
| --- | --- |
| [cc2api Backend Service Architecture](./service-architecture.md) | 当前合同与验证要求 |
| [cc2api Settings & Database](./settings-database.md) | 当前合同与验证要求 |
| [cc2api Backend Testing & Quality](./testing-quality.md) | 当前合同与验证要求 |
| [账号环境共同合同](../../orchestrator/backend/account-runtime-v3.md) | 数据身份与生命周期的权威位置 |

## Pre-Development Checklist

1. 阅读任务材料及本层相关规范，核对实际类型和调用入口。
2. 搜索所有路径和合同消费者，读取跨模块权威规范。
3. 核对源码路径与容器、宿主固定包路径的归属。
4. 测试使用合成凭据和离线回环。

## Quality Check

在仓库根执行以下命令。模块内命令以 `cd` 为界：

```bash
cd services/gateway
cargo fmt --check
cargo test --locked
```
