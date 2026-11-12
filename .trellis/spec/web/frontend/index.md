# Vue 管理后台规范

## 适用范围

apps/web/；Vue 3、TypeScript 和 Vite。

## Guidelines Index

| 规范 | 说明 |
| --- | --- |
| [cc2api Frontend Guidelines](./frontend-guidelines.md) | 当前合同与验证要求 |
| [设置与数据库](../../gateway/backend/settings-database.md) | 后端字段及 API 合同 |

## Pre-Development Checklist

1. 阅读任务材料及本层相关规范，核对实际类型和调用入口。
2. 搜索所有路径和合同消费者，读取跨模块权威规范。
3. 核对源码路径与容器、宿主固定包路径的归属。
4. 测试使用合成凭据和离线回环。

## Quality Check

在仓库根执行以下命令。模块内命令以 `cd` 为界：

```bash
npm --prefix apps/web ci
npm --prefix apps/web run build
```
