# implement.md

## Implementation Checklist

- [x] 读取 `orchestrator/main.py` 中普通 run、capture run、continue run 的现有启动路径。
- [x] 增加一个小的内部 helper，用于从 run 行解析 continue 是否应启用完整抓包以及 flows 目录。
- [x] 修改 `Runner.start_continue()`：在 capture run 分支挂载原 `flows_dir` 到 sidecar `/flows`。
- [x] 修改 `Runner.start_continue()`：在 capture run 分支设置完整抓包环境变量，非 capture run 保持原状。
- [x] 检查 continue cleanup 路径，确保新增挂载和 env 不影响失败清理。
- [x] 如有合适的测试框架，补充最小单元测试；否则补充可执行的本地/远程手工验证步骤。
- [x] 更新 README 中 continue 抓包行为说明，只描述索引可见和敏感数据注意事项。

## Validation

- [x] `python3 -m py_compile orchestrator/main.py`
- [x] `git diff --check`
- [x] `ast.parse` 检查 `orchestrator/main.py` 和 `images/sidecar/recorder.py`
- [x] 静态检查确认 continue capture 分支设置 `/flows` 挂载、`CAPTURE_FULL_HTTP=1`、`CAPTURE_MODE=continue_full_http`，普通 continue 保持 `SAVE_FULL_FLOWS` 默认值。
- [x] 用 stub 注入缺失依赖后导入 `orchestrator/main.py`，验证 `_resolve_capture_flows_dirs()` 对普通 run、capture run、仅 `capture_summary_path` 历史 run、缺失 `flows_dir` 的 capture run 均按预期分支处理。
- [x] 用 `BENCH_DATA=/data HOST_BENCH_DATA=/host/bench-data` 验证 `/data/flows/...` 能转换为宿主机 `/host/bench-data/flows/...`。
- [ ] 本地或远程启动一个 capture run，记录 `http_capture.jsonl` 和 `capture_index.json` 初始行数/entries 数。
- [ ] 对该 capture run 点击继续，输入 `/context` 或 `/cost`。
- [ ] 验证原 run flows 目录的 `http_capture.jsonl` 行数增加，`capture_index.json` entries 增加。
- [ ] 对普通非 capture run 点击继续，验证不会新增完整 `http_capture.jsonl`。
- [ ] 验证 `docker ps -a --filter name=bench-continue-` 没有失败残留容器。

备注：直接 import `orchestrator/main.py` 做函数级验证时，本地 Python 环境缺少 `docker` 包，未安装新依赖污染当前环境；已用 `py_compile`、`ast.parse` 和静态断言覆盖语法与关键路径。

## Review Gates

- 开始实现前：确认本任务范围只改 `vibecoding-bench` continue 抓包兼容，不混入 `cc2api count_tokens`。
- 完成实现后：先报告验证结果，再进入后续 check/commit 流程。
