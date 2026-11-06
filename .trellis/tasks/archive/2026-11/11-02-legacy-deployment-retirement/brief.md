# Brief — 旧版永久退役

## Goal

- 迁移验收后永久删除旧部署及挂载数据，不归档。

## Scope

- 退出 ai-fund 旧来源及仍指向旧入口的渠道。
- 清理旧容器 vibebench-orchestrator、docker-claude-code-gateway-1 和归属明确、无保护引用的旧镜像。
- 同时移除两个旧部署目录内已证明归属的旧备份、暂存和凭据副本；冻结实际文件名，保留源码父目录。
- 删除 /root/vibecoding-bench/data、核实无共享引用的旧 topics.md/webui 挂载，以及卷 docker_claude-code-gateway-data。

## Non-Goals

- 不动当前 v3、其他应用、共享挂载或整个源码父目录，不做全局 prune 或历史归档。

## Technical Overview

- 核对迁移收据、消费方和全部引用后冻结清单，逐项停止/删除并记录结果，最后检查健康和实际磁盘空间差。

## Context & Decisions

- 用户已授权约 7.4 GB 旧数据及其中账号、任务、运行和抓包永久删除；只保留无秘密的操作收据。

## Risks

- 旧渠道引用仍需取得实时核对结果；共享或未知资源不进入删除清单。删除后的旧数据不可恢复。

## Acceptance

- 目标旧资源不存在、没有归档，v3 与其他应用正常，来源和空间核查结果可审计。

## Next Step

- 迁移通过后，退出旧业务引用并冻结精确清理清单。
