# flower2api 编排服务

Python／FastAPI 编排服务，负责账号环境、任务调度、工程迭代、终端会话及系统更新的协调。HTTP 入口为 `main.py` 的 `app`，容器通过 `uvicorn main:app` 启动。

## 模块导航

当前模块和测试平铺在本目录，按职责查阅：

| 职责 | 主要模块 |
| --- | --- |
| HTTP 与应用生命周期 | `main.py` |
| 账号环境与隔离 | `account_runtime.py`、`account_isolation.py`、`credential_ownership.py`、`account_update_identity.py` |
| 终端与登录 | `login_terminal.py`、`login_drafts.py`、`pi_terminal.py` |
| 配额、时段和资源 | `cli_quota.py`、`quota_protocol.py`、`run_windows.py`、`resource_budget.py`、`cpu_resources.py` |
| 工程入口与存储 | `projects.py`、`projects_api.py`、`projects_store.py`、`projects_catalog.py`、`project_library.py` |
| 工程执行与迭代 | `projects_runtime.py`、`projects_pi.py`、`project_iteration.py`、`project_plans.py`、`project_development.py` |
| 工程验收 | `projects_verification.py`、`project_verifier.py`、`project_scenarios.py`、`project_native_regression.py` |
| 原生运行时与诊断 | `native_sender.py`、`native_kernel_upgrade.py`、`native_capture.py`、`runtime_diagnostics.py`、`process_metrics.py` |
| 数据库定义与迁移 | `database_schema.py`、`database_migrations.py`、`database_migration_contract.py`、`database-migration-registry.json` |
| 存储、备份与文件 | `storage_backup.py`、`storage_maintenance.py`、`storage_assets.py`、`runtime_files.py` |
| 系统更新 | `system_updates.py`、`system_update_contract.py`、`system_update_connection.py`、`system_update_gate.py` |
| 测试与夹具 | `test_*.py`、`testdata/` |

`project_*_observer.py` 是特定工程的行为观察器，与通用工程调度模块分别维护。其业务背景见 [工程库](../../resources/project-library/README.md)。

## 开发与验证

从仓库根建立 Python 3.12 虚拟环境：

```bash
python3 -m venv .venv
.venv/bin/pip install -r services/orchestrator/requirements.txt
PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest discover -s services/orchestrator
```

系统更新与发布相关测试另见 `deploy/flower2api/test_*.py`。数据库定义校验入口为：

```bash
python3 deploy/flower2api/verify_database_definitions.py
```

当前镜像把模块复制至 `/app`，固定宿主更新包也有显式文件清单。调整目录时需要同步 Python 导入、镜像复制和固定包清单，并验证仓库外独立导入。

## 部署与来源

正式平台通过 [联合部署](../../deploy/flower2api/README.md) 启动编排服务，与同批网关及账号镜像协作。配置、签名更新、备份和回退见 [系统更新 SOP](../../deploy/flower2api/SYSTEM-UPDATES.md)。

本目录沿原 vibecoding-bench v3 编排服务演进。迁移基线和路径映射见 [组件来源](../../docs/migrations/flower2api-sources.json) 与 [单仓说明](../../docs/migrations/flower2api-layout.md)。
