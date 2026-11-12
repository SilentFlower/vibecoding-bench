# 平台构建与部署规范

## 适用范围

deploy/、images/ 与 .github/workflows/；跨模块升级和发行合同。

## Guidelines Index

| 规范 | 说明 |
| --- | --- |
| [Auth Design (Cookie Session)](./auth-design.md) | 当前合同与验证要求 |
| [Image Build & GHCR Push](./image-build-push.md) | 当前合同与验证要求 |
| [Claude Code 官方协议抓包](./official-protocol-capture.md) | 当前合同与验证要求 |
| [v3 平台在线更新合同](./platform-online-update.md) | 当前合同与验证要求 |
| [Remote Deploy](./remote-deploy.md) | 当前合同与验证要求 |
| [账号环境共同合同](../../orchestrator/backend/account-runtime-v3.md) | 数据身份与生命周期的权威位置 |

## Pre-Development Checklist

1. 阅读任务材料及本层相关规范，核对实际类型和调用入口。
2. 搜索所有路径和合同消费者，读取跨模块权威规范。
3. 核对源码路径与容器、宿主固定包路径的归属。
4. 测试使用合成凭据和离线回环。

## Quality Check

在仓库根执行以下命令。模块内命令以 `cd` 为界：

```bash
python3 deploy/v3/verify_database_definitions.py
PYTHONPATH=services/orchestrator:deploy/v3 .venv/bin/python -m unittest discover -s deploy/v3
```
