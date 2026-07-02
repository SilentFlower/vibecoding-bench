# Deployment & Operations Guidelines

> 把镜像构建、DockerHub 发布、远程部署、鉴权运维等"代码之外"的可执行契约固化下来。

---

## Overview

本项目交付路径:**本地写代码 → 构建本地镜像 → 打 tag 推 DockerHub → 远程 git pull + docker compose pull + recreate**。每一步都踩过坑,这里把"必须这么做、否则会出 X 问题"的契约写清楚,避免重复踩。

镜像清单:
- `huajiwuyan/vibebench-orchestrator` — FastAPI 后端
- `huajiwuyan/vibebench-worker` — 跑题的 Claude Code 容器
- `huajiwuyan/vibebench-sidecar` — MITM + HTTP/SOCKS5 上游代理透明链路

远程参考实例: <http://186.244.215.29:8080/>(AWS EC2 + Docker + Caddy 未配)

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Image Build & Push](./image-build-push.md) | 三镜像构建、双 tag 策略、Dockerfile COPY 与 recreate 协同 | Filled |
| [Remote Deploy](./remote-deploy.md) | 4 件套部署清单、HOST_BENCH_DATA 解析、端口冲突、Security Group | Filled |
| [Auth Design](./auth-design.md) | Cookie session 中间件契约、为什么不用 Basic Auth、WS 间接保护 | Filled |

---

## How to Use

1. **第一次部署到新机器**:从头读 [Remote Deploy](./remote-deploy.md) 走 4 件套流程
2. **代码改了要发新版**:读 [Image Build & Push](./image-build-push.md) 走双 tag + recreate
3. **远程重启 cc2api / claude-code-gateway**:读 [Remote Deploy](./remote-deploy.md) 的 `cc2api.env` 场景
4. **加 / 改鉴权**:读 [Auth Design](./auth-design.md) 看中间件豁免规则与 API 契约

每个文件结尾的 **Common Mistakes** 是上次实际踩到的坑,新人先看那部分。

---

**Language**: 中文撰写;命令、文件名、字段名、镜像名保留英文以贴合实操。
