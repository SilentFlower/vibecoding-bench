# 反重力 Messages 思考档位与图片回包实施计划

## 执行顺序

1. 读取网关 Messages 转换、Gemini 账号目录档位和工具续轮合同。复用 `gemini_thinking_tier` 和目录选号，在 Messages 路径接入预算与 effort，并确认当前档位在续轮中绑定原型号。
2. 在 Messages 的 JSON 与 SSE 共用图片格式化规则。用同一合法图片源数据覆盖两种响应，校验文本、工具和思考签名在混合 Part 中的行为。
3. 用现有 `deploy/flower2api/verify_agy_native_loopback.py --messages-search` 扩展合成上游的真实二进制回环。用目录提供和缺少目标档位、显式模型、原工具续轮和实际含图片帧覆盖 AC1～AC3。用授权测试环境完成 AC4 或记录待验证的能力与条件。
4. 按 Pre-Check、Check-All、规范同步与精确推送流程完成交付。

## 验证

- 在 `services/gateway` 运行 `cargo fmt --check`、`cargo test --locked`，并构建本地网关、发送器供回环使用。
- 从仓库根运行 `PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest discover -s services/orchestrator -p 'test_agy*.py'`。
- 从仓库根运行 `.venv/bin/python deploy/flower2api/verify_agy_native_loopback.py --image flower2api-account:v3-agy-migration-verification --loader-root /lib/x86_64-linux-gnu --messages-search`，另用该脚本现有普通 Gemini 入口做回归。按证据区分合成帧、实际 AGY 二进制和真实授权上游。

## 影响与回退

- 主要改动在 `services/gateway/src/service/gemini/messages.rs`、`services/gateway/src/service/gemini.rs` 与回环用例。改动按本任务提交独立回退，原账号环境和私有发送协议沿既有合同。
