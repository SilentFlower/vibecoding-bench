# Claude Code MITM 完整抓包分析模式实现计划

## Implementation Checklist

- [ ] 阅读相关规范：backend、frontend、deploy/spec 索引中与 Python API、WebUI、Docker 环境变量相关的文档。
- [ ] 扩展 DB schema：给 `runs` 增加 `run_kind`、`capture_mode`、`capture_summary_path`，兼容旧 SQLite。
- [ ] 扩展 `Runner.start_run()`：支持 task dict 的 capture 标记，并仅对 capture run 强制开启完整 flow 和 HTTP JSONL 捕获环境变量。
- [ ] 扩展 `images/sidecar/recorder.py`：在 `CAPTURE_FULL_HTTP=1` 时写 `http_capture.jsonl` 和索引，提取 billing header、`cc_version`、`cc_entrypoint`、CCH/指纹相关字段。
- [ ] 新增后端模型和接口：`POST /api/captures/run`，必要时新增 `GET /api/runs/{rid}/capture`。
- [ ] 扩展 run 查询和 stats/detail 返回：让前端能识别 capture run。
- [ ] 扩展 WebUI：在 runs tab 增加 `topic + account` 抓包启动表单，并在列表/详情中展示 capture 标记和抓包文件。
- [ ] 更新 README 或 doc：说明使用步骤、输出路径、敏感数据风险、后续如何用于版本差异分析。
- [ ] 添加或更新验证脚本/手动验证记录。

## Validation

- `python3 -m py_compile orchestrator/main.py images/sidecar/recorder.py`
- 如果环境可用：`docker compose --profile build build sidecar-image orchestrator`
- 如果已有服务可用：启动一次 capture run，检查：
  - `data/flows/<account>/<task_id>/<run_id>/stats.jsonl`
  - `data/flows/<account>/<task_id>/<run_id>/http_capture.jsonl`
  - `data/flows/<account>/<task_id>/<run_id>/capture_index.json`
- 前端手动验证：
  - runs tab 可选择账号和 topic 启动 capture run；
  - run 列表显示 capture 标记；
  - run 详情能看到抓包区块。

## Review Gates

- 开始实现前：用户已确认抓包资产默认保存请求体全文和响应体全文。
- 完成后：确认普通 run 默认行为未变，capture run 才生成完整抓包资产。
