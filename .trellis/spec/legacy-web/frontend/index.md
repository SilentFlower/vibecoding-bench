# 工程静态界面规范

## 适用范围

apps/legacy-web/；原生 JS 页面及独立环境视图。

## Guidelines Index

| 规范 | 说明 |
| --- | --- |
| [Component Guidelines](./component-guidelines.md) | 当前合同与验证要求 |
| [Directory Structure](./directory-structure.md) | 当前合同与验证要求 |
| [Hook Guidelines](./hook-guidelines.md) | 当前合同与验证要求 |
| [Quality Guidelines](./quality-guidelines.md) | 当前合同与验证要求 |
| [State Management](./state-management.md) | 当前合同与验证要求 |
| [Type Safety](./type-safety.md) | 当前合同与验证要求 |
| [账号环境共同合同](../../orchestrator/backend/account-runtime-v3.md) | 数据身份与生命周期的权威位置 |

## Pre-Development Checklist

1. 阅读任务材料及本层相关规范，核对实际类型和调用入口。
2. 搜索所有路径和合同消费者，读取跨模块权威规范。
3. 核对源码路径与容器、宿主固定包路径的归属。
4. 测试使用合成凭据和离线回环。

## Quality Check

在仓库根执行以下命令。模块内命令以 `cd` 为界：

```bash
node --check apps/legacy-web/app.js
node --check apps/legacy-web/projects.js
node --check apps/legacy-web/environments.js
```
