# 运行时诊断页面规范

## 适用范围

services/runtime/web/；原生 HTML/CSS/TypeScript 页面。

## Guidelines Index

| 规范 | 说明 |
| --- | --- |
| [日志页面状态合同](./state-management.md) | 当前合同与验证要求 |

## Pre-Development Checklist

1. 阅读任务材料及本层相关规范，核对实际类型和调用入口。
2. 搜索所有路径和合同消费者，读取跨模块权威规范。
3. 核对源码路径与容器、宿主固定包路径的归属。
4. 测试使用合成凭据和离线回环。

## Quality Check

在仓库根执行以下命令。模块内命令以 `cd` 为界：

```bash
cd services/runtime
bun run typecheck
bun run build
bun run test:ui
```
