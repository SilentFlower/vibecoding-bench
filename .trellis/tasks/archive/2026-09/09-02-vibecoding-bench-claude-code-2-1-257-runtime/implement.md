# 实施计划

## 1. 同步运行时默认值

- [x] 更新 `images/worker/Dockerfile` 和 `images/worker/entrypoint.sh` 为 2.1.257。
- [x] 更新 `orchestrator/main.py` 的环境 fallback 与内嵌 Node fallback。
- [x] 核对普通 task、抓包、OAuth/login、quota worker 均显式传递最终版本。

## 2. 同步配置与界面

- [x] 更新 `docker-compose.yml`、`docker-compose.remote.yml` 和 `.env.example`。
- [x] 更新 `webui/index.html` placeholder/datalist，保留旧版本回滚示例。
- [x] 更新 `README.md`、`image-build-push.md` 和 `remote-deploy.md` 的当前默认版本。

## 3. 测试与审计

- [x] 更新 `orchestrator/test_main.py` 默认版本与所有 worker 类型的传递断言。
- [x] 运行 `python3 -m unittest orchestrator.test_main`。
- [x] 运行 `docker compose -f docker-compose.yml --env-file .env.example config --quiet`。
- [x] 运行 `docker compose -f docker-compose.remote.yml --env-file .env.example config --quiet`。
- [x] 使用 `rg` 检查遗留 2.1.220，仅保留历史任务、旧画像或明确回滚示例。
- [x] 执行 Check-All 并修复发现的问题。

## 风险与回滚点

- 任一内嵌 Node fallback 漏改会在凭据恢复等少见路径写入旧版本身份。
- 只更新镜像预装、不更新 orchestrator 环境会导致 worker 启动时再次安装旧版本。
- 生产 WebUI 可能保存了显式 2.1.220；代码升级不会自动覆盖，发布子任务必须核对。
