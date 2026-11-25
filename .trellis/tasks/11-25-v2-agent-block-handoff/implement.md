# 实施与验证

1. 扩展 `images/account/test_tui_session.py` 的真实事件序列。现有 `_offered` 会直接完成父轮，应补上先关闭第一个工具块、保持第二个块未完成的测试。同步点用事件控制。覆盖早到/晚到回执、追加消息及同时重试。
2. 在 `images/account/tui_messages.py` 与 `tui_session.py` 对齐工具块、派工、认领和终态生命周期。复核 `tui_source.py` 及 Rust 私有 prepare 的截止与断连传递，仅在现有边界确有缺口时改动。
3. 补错配、无回执、容量、重复提交、终止清理、旧前台及嵌套 Agent 回归。验证子请求不会占用父工具回执所需的最后一个名额。使用隔离时钟或受控流跨越旧 2 秒窗口，真实链路复验此次约 14 秒时序。
4. 对照固定 CC 的后台 Agent 与定向 SendMessage，走公开 Messages、真实 Gateway 和 account-sender 到合成上游，记录父流结束、首个子请求、回执到达和模型提交次数。
