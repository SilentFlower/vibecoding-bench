#!/usr/bin/env bash
# 同一管理镜像按角色运行；内部数据库始终分目录。
set -euo pipefail
case "${V3_ROLE:?需要 V3_ROLE}" in
  gateway) exec /app/claude-code-gateway ;;
  orchestrator) exec uvicorn main:app --host 0.0.0.0 --port 8000 ;;
  *) exit 2 ;;
esac
