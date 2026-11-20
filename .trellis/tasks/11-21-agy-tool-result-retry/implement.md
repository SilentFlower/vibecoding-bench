# 实施与验证

1. 按已观测的九条内容和最后四个无 ID 同名工具构造合成正文。在现有断网回环加一项覆盖首笔接续中和首条工具 SSE 后的重复提交。先记录当前版本 400 和真实提交数。
2. 在 `gemini.rs` 实现已受理续轮的登记与同响应读取。维护领取、尚未发送、已开始和已结束边界，复用现有 SSE / JSON 格式化及错误转换。沿当前请求诊断添加重读原请求关联和受控拒绝分类，兼容旧诊断 JSON。
3. 核对 `verify_agy_gemini.py` 和 `verify_agy_native_loopback.py` 中对完全同正文重复请求的断言。保留重复 ID、部分回填、跨账号访问和并发错配的现行拒绝。补纯文本首帧、普通 JSON、原失败、并发断开、重试截止和资源预算定向用例。
4. 运行 `cargo fmt --check` 和 `cargo test --locked`。用当前网关和账号发送器二进制运行 `verify_agy_gemini.py --image <隔离测试镜像>`，以及 `verify_agy_native_loopback.py --parallel-tools`、`--tool-deadlines`、`--png` 和默认回环。实测完整工具链与 SQLite 诊断，记录真实模型与工具回填次数、响应是否一致、容量压力下首次响应和释放情况。
5. 完成 Check-All 后同步 AGY 运行合同和诊断规范的对应段落，按任务精确变更范围交接提交。相邻账号运行规范工作区修改按原有归属核对。
