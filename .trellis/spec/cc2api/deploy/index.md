# cc2api Deploy Code-Spec Index

> 本层覆盖 `cc2api/` 构建、Docker 镜像、远程部署、环境变量和发布验证。协议行为见 `protocol/`，代码实现见 `backend/` / `frontend/`。

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Deploy Guidelines](./deploy-guidelines.md) | 前后端构建、Docker compose、远程部署、DB/账号迁移和验证命令 | Filled |

---

## Pre-Development Checklist

修改构建、镜像、环境变量、远程部署或 `cc2api.env` 前必须：

1. 读取 [Deploy Guidelines](./deploy-guidelines.md)。
2. 确认 `cc2api/` 子模块提交是否已推送到 `origin/main`。
3. 涉及默认 Claude Code 版本或账号画像时，同时读取 [protocol](../protocol/index.md)。
4. 涉及前端资源嵌入时，同时运行后端和前端构建验证。

## Quality Check

根据改动范围选择：

```bash
cd cc2api
cargo fmt --check
cargo test
cd web && npm run build
```

远程部署后必须验证：

```bash
curl http://127.0.0.1:<port>/
```

以及必要的 DB settings / account version 分布。

---

**Language**: 中文撰写；镜像名、环境变量、命令和路径保留原文。
