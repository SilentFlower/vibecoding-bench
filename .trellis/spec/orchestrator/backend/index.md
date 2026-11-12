# 编排服务规范

## 适用范围

services/orchestrator/ 的 Python 服务、数据库、账号运行环境和工程调度。

## Guidelines Index

| 规范 | 说明 |
| --- | --- |
| [v3 固定账号运行环境契约](./account-runtime-v3.md) | 当前合同与验证要求 |
| [Database Guidelines](./database-guidelines.md) | 当前合同与验证要求 |
| [Directory Structure](./directory-structure.md) | 当前合同与验证要求 |
| [Error Handling](./error-handling.md) | 当前合同与验证要求 |
| [Logging Guidelines](./logging-guidelines.md) | 当前合同与验证要求 |
| [项目迭代模式契约](./project-iterations.md) | 当前合同与验证要求 |
| [Quality Guidelines](./quality-guidelines.md) | 当前合同与验证要求 |
| [Topic Prompt Contract](./topic-prompt-contract.md) | 当前合同与验证要求 |

## Pre-Development Checklist

1. 阅读任务材料及本层相关规范，核对实际类型和调用入口。
2. 搜索所有路径和合同消费者，读取跨模块权威规范。
3. 核对源码路径与容器、宿主固定包路径的归属。
4. 测试使用合成凭据和离线回环。

## Quality Check

在仓库根执行以下命令。模块内命令以 `cd` 为界：

```bash
PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest discover -s services/orchestrator
```
