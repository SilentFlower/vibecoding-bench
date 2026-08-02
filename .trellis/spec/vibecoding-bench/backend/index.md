# Backend Development Guidelines

> Best practices for backend development in this project.

---

## Overview

本项目后端是一个**单进程 FastAPI 服务**(`orchestrator/main.py`),用 docker SDK 编排 worker + sidecar 容器,数据落 SQLite。无 ORM、无 migration 系统、无任务队列、无单元测试 —— P1 阶段刻意保持极简。

所有规范文件:
- **诚实描述代码实际是什么样**,而非"理想中应该是什么样"
- **中文撰写**,代码示例保留原文
- 配套 `orchestrator/main.py` 当前提交;实现风格如有偏离需更新本目录

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Directory Structure](./directory-structure.md) | 单文件 main.py 内部分节 + 何时拆包 | Filled |
| [Database Guidelines](./database-guidelines.md) | 裸 sqlite3、_SCHEMA、_db_lock、参数化、无 migration | Filled |
| [Error Handling](./error-handling.md) | HTTPException + 清理路径吞异常的两套策略 | Filled |
| [Quality Guidelines](./quality-guidelines.md) | 禁用模式 / 必用模式 / 真跑验收 / Review 清单 | Filled |
| [Logging Guidelines](./logging-guidelines.md) | P1 不写 log,uvicorn + stats.jsonl 兜底 | Filled |
| [Topic Prompt Contract](./topic-prompt-contract.md) | Topic prompt 模式、API 字段、持久化与调度一致性 | Filled |

> 镜像构建 / GitHub Actions 与 GHCR 发布 / 远程部署 / Cookie session 鉴权契约,移到独立的 [deploy/](../deploy/index.md) 层,见那边的 image-build-push / remote-deploy / auth-design 三个 spec。本目录只覆盖 orchestrator 内部代码规范。
> `cc2api/` 是 Git submodule,协议升级规范见 [cc2api/protocol](../../cc2api/protocol/index.md),不要塞进本目录。

---

## How to Use These Guidelines

1. **写代码前**:看对应 spec 文件 + `orchestrator/main.py` 同类代码,贴着现有风格写
2. **改代码后**:对照 Code Review Checklist(quality-guidelines.md 末尾)逐项过一遍
3. **发现偏差**:如果代码现实和 spec 描述不一致,**先确认哪个是真相**(通常代码是真相),然后更新 spec(走 `trellis-update-spec`),不要默默改代码迎合过时 spec

每个文件结尾都有"Common Mistakes"表,**新人优先看这里**。

---

**Language**: Spec 主体使用 **中文**;表标题、字段名、模式名保留英文以贴合代码;示例代码不翻译。
