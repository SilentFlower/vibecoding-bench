# 编排服务目录规范

## 当前结构

`services/orchestrator/` 是 Python 服务模块。入口 `main.py` 负责 FastAPI 配置、调度与路由组合；账号运行时、数据库、工程执行及更新协议已经有独立模块。修改前读取实际模块与测试。

| 路径 | 职责 |
| --- | --- |
| `main.py` | 应用入口、配置、兼容调度及路由组合 |
| `account_runtime.py`、`account_isolation.py` | 固定账号环境与隔离 |
| `database_schema.py`、`database_migrations.py` | 冻结数据库定义及迁移 |
| `projects*.py`、`project_*.py` | 工程目录、终端、评审、内容合同和执行 |
| `system_update*.py` | 更新合同、门禁和控制端连接 |
| `test_*.py`、`testdata/` | unittest 与冻结测试资料 |
| `requirements.txt` | Python 运行依赖 |

仓库级工具位于 `scripts/`，角色脚本与容器定义位于 `images/`，跨组件构建与验证位于 `deploy/v3/`。题库和工程种子位于 `resources/`，两套界面位于 `apps/`。实际部署路径通过 `deploy/v3/source_layout.py` 映射。

## 模块组织

沿现有职责修改对应模块。新增资源路由由既有路由组合入口接入。对现有公共合同保留一个权威实现和测试入口。方法保持合理复杂度，独立职责和实际复用需求决定拆分。

## Naming Conventions

- **文件名**:全部小写 + 下划线,如 `main.py`、`init-account.sh`(脚本可用短横线)
- **Python 类**:`PascalCase`,如 `Runner` / `Scheduler` / `LoginSession` / `LoginManager`
- **Python 函数 / 变量**:`snake_case`,如 `load_topics` / `init_db` / `run_id`
- **Python 私有**:单下划线前缀,如 `_db_lock` / `_SCHEMA` / `_ACC_NAME_RE` / `_sem()`
- **常量**:`UPPER_SNAKE`,如 `BENCH_DATA` / `WORKER_IMAGE` / `PER_ACCOUNT_CONCURRENCY` / `SIDECAR_BOOT_WAIT`
- **正则**:`_NAME_RE` 后缀,模块级常量(`_CAT_RE` / `_ITEM_RE` / `_ACC_NAME_RE`)
- **Docker 容器命名**:`bench-<role>-<id>`,如 `bench-sidecar-<run_id>` / `bench-worker-<run_id>` / `bench-login-sidecar-<sid>` / `bench-login-worker-<sid>`(`bench-login-*` 前缀用于启动时一键清残留)

**API 路径**:
- 全部挂在 `/api` 前缀下(`/` 留给静态 WebUI)
- 资源用复数:`/api/accounts`、`/api/tasks`、`/api/runs`、`/api/topics`
- 子资源:`/api/runs/{rid}/transcript`、`/api/runs/{rid}/files`、`/api/runs/{rid}/stats`
- 流端点:`/api/runs/stream`(SSE)、`/api/accounts/login/ws/{sid}`(WebSocket)
- 动作端点:HTTP 动词不够时退化到 RPC 风格,如 `/api/accounts/login/start`、`/api/accounts/login/{sid}/commit`、`/api/accounts/login/{sid}`(DELETE = 取消)

---

## Examples

- **典型资源 CRUD**:`services/orchestrator/main.py` 的 accounts 路由组(`create_account` / `list_accounts` / `delete_account`)是后端 REST 端点的标准范式
- **后台 run 调度**:`Scheduler._execute()` 展示了"DB 状态机 + 信号量 + 兜底清理"的写法
- **PTY ↔ WebSocket 桥**:`login_ws()` 是异步双向流的范式参考
- **正则解析外部数据**:`load_seed_topics()` + `_CAT_RE` / `_ITEM_RE` 是"用正则把 Markdown 当结构化 seed 数据读"的样例
