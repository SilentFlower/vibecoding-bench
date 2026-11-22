# 已有证据与接续入口

## 授权和基线

- 固定原版AGY1.5.9，SHA256：39816d49d5ab92229952987225c23ea3fed7580699dcb4a444e0388e0ac1ce43。
- 账号原生consumer OAuth登录态保存在独立HOME，原生文件权限0600，具有访问令牌、刷新令牌和到期时间。
- 新CLI进程复用登录态，gemini-3.8-flash-low成功返回AGY_DIRECT_OAUTH_OK。可用模型18档，包含Gemini4、Gemini3.8、Claude5.5与GPT-OSS。
- 无秘密证据在本机/root/.local/state/agy-deployment/oauth-study/baseline-evidence；说明为同目录OAUTH_BASELINE.md。真实凭据只属于服务器账号环境。
- 服务器原生测试容器agy-oauth-test-159，账号环境目录/opt/agy-runtime/oauth-test-1.5.9。旧渠道138已停用，旧代理测试容器停止。
- 旧压缩研究包的495字节重建差异待核对；直接OAuth基线使用已核验的完整原版执行体。

## CC参照

- services/gateway/src/service/native_runtime.rs通过CLAUDE_CODE_OAUTH_TOKEN注入AT。
- services/gateway/src/service/gateway.rs及service-architecture规范已有有界oauth_recovery。
- account-runtime-v3规范规定单一RT所有权、活动门禁、代次、失败对账及当前HOME保护。
- 当前源目录存在尚在开发的集群文件。用户指定的6d4253a基准中cluster_login_contract.py缺失，后续以目标工作树实际代码为准。

## 同形体研究

来源仓库/root/project/new-api，仅作为现有研究和代码参考：
- scripts/system-prompt-worker/src/index.mjs：固定ASCII字母到非ASCII同形字符映射与系统文本定位。
- scripts/system-prompt-worker/src/gemini-stream.mjs：流式字段定位。
- scripts/system-prompt-worker/test/worker.test.mjs：固定映射、重复处理、普通/流式一致和角色隔离。
- .trellis/spec/backend/system-prompt-worker.md及11-15-system-prompt-worker规划。

现有映射为确定替换；转换后的非ASCII不再次命中，Unicode码点数保持。token成本和缓存效果需要真实用量验证。旧Worker还包含用户文本句末星号和其它模式；本任务明确采用默认关闭的AGY系统同形体策略。

## 当前总验收接续

当前基线64d72ce633d26734779579c96d1d586226313ad3。五个子任务均completed/closed且已在当前分支交付。父任务保持planning，当前用户要求开始总验收与收尾。

原创建基准6d4253a29f7a0ee6bbadc0809d5acb570b14781f及早期交接保留为历史来源。当前以research/acceptance-inventory.md、五子项task.json及已提交实现为总验收依据。

凭据研究合同路径为../../11-18-agy-managed-credential-contract/research/credential-contract.md。本轮真实外部模型预算0；当前产品真实Google登录、实际到期及费用效果保留后续独立授权验收。完整Brief评审后激活父任务工程总验收。
