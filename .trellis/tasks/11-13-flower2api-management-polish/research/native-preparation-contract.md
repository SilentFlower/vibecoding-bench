# 原生准备投影合同摘录

权威来源：.trellis/spec/orchestrator/backend/account-runtime-v3.md的“V3原生sender共享映像池与资源预算”Contracts；本文件为任务上下文摘要。

- 网关批量GET /admin/native-preparations是最多4096项对象数组，以正整数account_id建立映射；读取错误返回read_failed。
- 环境ID/generation与本地native.kernel_generation必须匹配；checked_at_ms为整数且当前时间差在0至45000毫秒之间。
- ready还需正PID和正idle_workers。身份错误、过期或损坏字段必须保持未知，不能显示旧PID和旧数量。
- legacy账号和草稿不显示原生准备。stopped显示sleeping。采集TLS状态与原生进程状态保持各自语义。
- 网关现有快照包含checking布尔信号；投影目前缺少检查中与等待同代快照的明确信息。U3/U4拟增加最小可选展示字段，所有旧身份保护继续生效。
- 原协调器20秒巡检；环境页20秒读取快照。页面读取不触发准备、唤醒、重建或真实模型请求。
- 现有测试锚点：services/orchestrator/test_account_runtime.py约175至205行，deploy/flower2api/verify_environment_ui.py约265至285行。
