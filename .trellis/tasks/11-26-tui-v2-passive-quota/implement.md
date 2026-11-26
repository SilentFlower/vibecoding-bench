# V2 官方额度修复实施计划

## 顺序

1. 核对开始时的脏文件基线。以 `images/account/tui_sender_launch.py`、`tui_session.py`、`tui_source.py` 及错误类型定义为起点，将真实响应中的白名单额度带到 V2 私有头。使用普通、错误和流式回执的既有输出路径。
2. 在 `services/gateway/src/service/tui_sender.rs` 接收并约束私有样本。核对经 `runtime_transport.rs` 的公开投影。接入 `gateway.rs` 的 V2 响应分支，复用已有网关额度解析和 `account.rs` 的持久化流程。沿原请求关联同一个账号。
3. 扩展既有 Python 源端和 Rust 私有发送器测试，使用合成授权与回环模型。补充公开 `/v1/messages` 至 `GET /admin/accounts` 的回归断言。包含 200 流式与 JSON、工具续轮、429、未观测周窗、旧发送器及其他账号隔离。核对私有头的大小边界与公开响应头过滤。
4. 运行定向及受影响回归。基线已有的变动按行核对，保留同文件内的独立工作。

## 验证命令

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=images/account:services/orchestrator python3 -m unittest test_tui_sender_launch test_tui_source test_tui_session
cargo test --locked --manifest-path services/gateway/Cargo.toml --lib service::tui_sender::tests
cargo test --locked --manifest-path services/gateway/Cargo.toml --lib passive_usage
cargo fmt --check --manifest-path services/gateway/Cargo.toml
cargo test --locked --manifest-path services/gateway/Cargo.toml
```

公开路径用隔离 HTTP 夹具执行并核对管理读回。记录各笔响应状态、模型提交次数和对应账号的额度观测。真实线上请求的额度响应头另行核对。
