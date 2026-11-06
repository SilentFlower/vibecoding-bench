# 调研结论（2026-11-02）

## 官方分级

来源：https://support.claude.com/en/articles/17728952-what-is-the-ultra-plan 。Max 20x 自动转为 Ultra；只有已验证 Ultra 无 5h 限制，仍有周额度与 Fable 限制。网页名称不证明 OAuth 内部协议字段已更名。

## 套餐代码

- cc2api 账号 `subscription_type` 为可选字符串；没有独立真实 rateLimitTier 持久字段。
- `rewriter.rs:3808` 与 `telemetry.rs:2068` 有重复分级推导：max 一律映射 20x。
- bench `_read_bench_profile_identity`（`main.py:905`）读取 subscriptionType，未传 rateLimitTier；创建 cc2api（`main.py:9288`）只使用前者。
- `Accounts.vue:1423` 套餐按钮缺 Ultra。
- ai-fund `worker/src/pools.js:532` 的 claudeSubscription 与 `frontend/src/views/Pools.vue:506` 不认识 ultra。直接对 normalizeClaudeAccount 执行合成输入验证后为 null；没有网络请求。
- 当前 v3 的普通额度拒绝检查（`account.rs:2790`、`:2829`）依赖有效数字与未来重置时间，缺失 5h 窗口本身不会触发此控制线，不能把所有相关逻辑笼统判定为错误。
- ai-fund 归一化（`pools.js:409`）可能在只有控制线、无真实窗口时仍展示 5h 窗口；需要区分无当前窗口与采样未知，不能靠 Ultra 名称自动清掉实际限制。

## 9-17 线上检查

- 旧版数据根 `/root/vibecoding-bench/data`，目标 `/srv/vibebench-v3-us/bench`；网关数据分别为旧 Docker volume 与 `/srv/vibebench-v3-us/gateway`。
- 原 bench ID 22、gateway ID 42，active；完整 profile 与网关 AT/RT 比较相同，Access Token 尚有效。检查时原运行计数为 1，原配置为并发 4、RPM 40。
- profile 的官方字段仍为 max/default_claude_max_20x。CLI 设备格式合法，账号 UUID 与网关相同；旧 API device_id 与原 CLI userID 不同。
- 目标不存在同名账号/profile/同身份网关账号。
- v3 同步检查 `main.py:9303` 与 `account_runtime.py:2639` 要求设备一致。首次 HOME 凭据镜像（`account_runtime.py:815`）可以继承原 profile/.claude.json，无须重新授权。
- 已绑定 v3 的 HOME 和 runtime 仅发布 AT，网关拥有 RT 和刷新权。源/目标跨实例交接不能简单复制之后让两侧同时运行。
- 本次未调用 OAuth 刷新/登录接口、未停止运行、未复制凭据或创建目标账号。完整运维收据为本机私有目录 `.deploy/ultra-9-17-inspection-20261102/`，不将任何凭据加入任务材料。

## 范围决定

用户接受推荐范围：仅迁账号登录态、原 CLI 身份、代理与配置，历史任务、会话、工作目录和抓包不迁入 v3。用户随后明确选择删除旧版、不归档，替代先前的旧版可查安排。无需迁移这些历史外键与运行路径，也不能复制整份旧数据库接管 v3。
