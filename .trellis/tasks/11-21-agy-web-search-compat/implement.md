# 反重力 Messages 适配实施清单

1. 验证固定 `agy 1.5.9` 在隔离回环中的模型选择、有限工具声明、`search_web` 输出和终态。保留脱敏协议证据。
2. 在 Rust 网关接入 Messages 的反重力分流。将当前 Gemini 执行边界提取为进程内调用点，复用鉴权、Session ID、模型权限、账号许可、传输、工具回填与重读。组装 Claude SSE 和 JSON。
3. 经 AGY 发送器接入本次搜索。原工具轮与关联搜索协调账号许可，使用原运行环境和代理。明确搜索空结果、错误、拒绝、重复与进程清理。
4. 回归常用 Claude Code 多轮、图片和客户端函数。验证纯搜索的 SSE 与普通 JSON、原始 Session ID、单并发与多账号、跨令牌隔离。使用当前仓库的 Gemini 发送器夹具和原版 TLS 回环，真实搜索使用已有授权的测试环境。

## 验证入口

- `cd services/gateway && cargo fmt --check && cargo test --locked`。覆盖 Messages 转换、Gemini 回填以及账号发送器相关测试。
- `PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest discover -s services/orchestrator`。覆盖 AGY 原版运行和私有传输回归。
- 在隔离环境以 `verify_agy_native_loopback.py --messages-search` 核对原版搜索与 Messages。分别验证允许域、禁止域和无规则下的直链及 Google 跳转链接。用 `--claude-code <本地 Claude Code 可执行路径>` 连同真实客户端复现 WebSearch 回填。运行既有 Gemini 回环覆盖相同发送器。单独记录实际外网查询的验证程度。
