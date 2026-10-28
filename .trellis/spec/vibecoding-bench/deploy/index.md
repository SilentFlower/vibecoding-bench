# Deployment & Operations Guidelines

> 把镜像构建、GitHub Actions / GHCR 发布、远程部署、鉴权运维等"代码之外"的可执行契约固化下来。

---

## Overview

本项目交付路径:**本地写代码与验证 → push main → GitHub Actions 构建并推 GHCR → 远程 git pull + docker compose pull + recreate**。每一步都踩过坑,这里把"必须这么做、否则会出 X 问题"的契约写清楚,避免重复踩。

镜像清单:
- `ghcr.io/silentflower/vibebench-orchestrator` — FastAPI 后端
- `ghcr.io/silentflower/vibebench-worker` — 跑题的 Claude Code 容器
- `ghcr.io/silentflower/vibebench-sidecar` — MITM + HTTP/SOCKS5 上游代理透明链路

远程参考实例: <http://186.244.215.29:8080/>(AWS EC2 + Docker + Caddy 未配)

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Image Build & Push](./image-build-push.md) | 三镜像构建、双 tag 策略、Dockerfile COPY、recreate 与 worker 首次引导契约 | Filled |
| [Remote Deploy](./remote-deploy.md) | 4 件套部署清单、HOST_BENCH_DATA 解析、端口冲突、Security Group | Filled |
| [Auth Design](./auth-design.md) | Cookie session 中间件契约、为什么不用 Basic Auth、WS 间接保护 | Filled |
| [Claude Code 官方协议抓包](./official-protocol-capture.md) | 权限模式/模型矩阵、正式代理链路、限频、CCH / 后缀、条件头与索引盲区、TLS 采集边界 | Filled |
| [v3 固定账号环境与交付](../backend/account-runtime-v3.md) | 两镜像联合清单、独立 Compose/端口/数据、生命周期、本地隔离验收与部署后旧镜像回收 | Filled |

---

## How to Use

1. **第一次部署到新机器**:从头读 [Remote Deploy](./remote-deploy.md) 走 4 件套流程
2. **代码改了要发新版**:读 [Image Build & Push](./image-build-push.md) 确认 workflow 双 tag 发布成功后再 recreate
3. **远程重启 cc2api / claude-code-gateway**:读 [Remote Deploy](./remote-deploy.md) 的 `cc2api.env` 场景
4. **加 / 改鉴权**:读 [Auth Design](./auth-design.md) 看中间件豁免规则与 API 契约
5. **升级 Claude Code 或核对 cc2api wire 画像**:读 [Claude Code 官方协议抓包](./official-protocol-capture.md)，按正式链路生成当前版本基线和模式矩阵
6. **部署 v3 或清理旧镜像**:读 [v3 部署成功后的旧镜像回收](../backend/account-runtime-v3.md#scenario-v3-部署成功后的旧镜像回收)，每次部署健康验收后定向回收，保留当前批次、最近两个完整历史批次及全部容器引用的镜像，再复核空间与服务

每个文件结尾的 **Common Mistakes** 是上次实际踩到的坑,新人先看那部分。

---

**Language**: 中文撰写;命令、文件名、字段名、镜像名保留英文以贴合实操。
