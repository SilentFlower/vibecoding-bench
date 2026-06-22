# 实施计划

## 步骤

1. 后端配置
   - 增加思考预算枚举和规范化 helper。
   - 增加 `get_runtime_effort_setting()`、`effective_runtime_effort()`、`save_runtime_effort_setting()`。
   - 增加 `GET/PUT /api/settings/runtime-effort`。
   - 在 `Runner.start_run()` 中只让普通 run / 批量 run 使用页面覆盖，抓包 run 保持环境兜底。

2. 前端配置
   - 在 runs 页增加思考预算配置面板。
   - 增加 `state.runtimeEffort`、加载、渲染、保存和重置逻辑。
   - 复用或泛化现有 runtime setting 样式。

3. worker timeout 识别
   - 扩展 API stall 检测，让 transcript 中的 API retry / timeout 文案参与 watchdog。
   - 扩展完成分类，synthetic `Request timed out` API error 不再算成功。
   - 主循环对该分类写入失败状态并以失败退出。

4. 文档
   - 更新 `.env.example`。
   - 更新 `README.md`。
   - 更新 `.trellis/spec/vibecoding-bench/deploy/remote-deploy.md` 或 image build spec 中的运行参数说明。

## 验证命令

- `python3 -m py_compile orchestrator/main.py`
- `bash -n images/worker/entrypoint.sh`
- `docker compose config`
- `docker compose -f docker-compose.remote.yml --env-file .env config`
- `git diff --check`

如时间允许，补充一个临时 API contract 验证：

- `GET /api/settings/runtime-effort`
- `PUT /api/settings/runtime-effort` 保存 `medium`
- `PUT /api/settings/runtime-effort` 保存非法值应返回 400
- `PUT /api/settings/runtime-effort` 清空后回退 `.env`

## 风险点

- `Runner.start_run()` 同时覆盖普通 run 和抓包 run，必须保持抓包分支隔离。
- `classify_claude_completion` 是 worker 成功判定核心，新增失败分类不能影响正常最终总结。
- 前端是零构建三文件，不引入 npm / bundler。
