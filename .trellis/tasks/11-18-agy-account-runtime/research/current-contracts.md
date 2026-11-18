# AGY运行环境接入的源码核对

## 已完成依赖

- 账号授权实现为f2d9c4c6，完成记录为6f82ec62。Account.platform、AGY凭据状态代次、AT/RT/expiry的权威存储和按账号同形体开关已经落地。
- 统一凭据研究见../../11-18-agy-managed-credential-contract/research/credential-contract.md。常驻TokenSource缓存旧AT；新worker采用新代，原worker保留在途及工具归属。
- 上一任务用户明确取消本轮人工Google登录验收前置。真实登录、身份和刷新保持未验证，由后续有授权账号的外部验证补齐。旧模型实验8次预算已经耗尽，本任务规划不执行真实模型调用。

## 仓库实际接线

- services/gateway/src/handler/router.rs:298-315：现有Router合并旧路由和gateway_fallback，尚未定义Gemini生成入口。新路由需显式注册并复用ApiToken权限及维护中间件。
- services/gateway/src/middleware/auth.rs:9-28：extract_key目前接受x-api-key及Authorization Bearer。Gemini兼容的x-goog-api-key/query key需要单独限定到新增路由及日志脱敏边界，旧入口保持原合同。
- services/orchestrator/account_runtime.py:630：AccountRuntime.ensure绑定CC版本、画像和固定账号角色；:1276的transport及existing_transport持有现有部署接线。AGY通过平台适配复用部署、代理、资源及生命周期控制。
- services/orchestrator/native_sender.py：固定280/293分发身份和预算，属于CC合同。AGY版本及资源分项独立验证，不能套用CC常量。
- services/orchestrator/agy_auth.py:413-419：AT-only原生models和GetUserStatus生成有来源能力，模型显示名称与原生执行ID映射仍须运行层核验。

## 现存私有研究原型

只读源位于/root/.local/state/agy-deployment/preserved/package，选定源码身份见prototype-source-identity.json。正式实现需冻结可复现源码/制品并进入正常镜像staging，禁止依赖开发机私有绝对路径。

- kernel.py:187-260：NDJSON内核、worker_ready、request_accepted、取消及待工具回填归属；continuation_results匹配原始Gemini历史并回填原worker。
- gemini_contract.py:122-164：目前只接受一个固定模型；generationConfig仅允许maxOutputTokens。文本、系统文本、函数声明、functionCall/functionResponse和签名存在独立解析。模型映射、所有未验证字段和错误传播需要正式接入审计。
- README.md对工具的“不支持”描述早于当前源码，不能以README代替现存实现证据；原型代码本身也不能代替验收。
- native_bridge.py:88-91及storage.py:68起：原型默认GEMINI_API_KEY和测试CA。正式版本必须接入管理侧发布的AT-only OAuth工作副本，正式路径使用正常证书校验，测试CA仅限隔离验证。
- image_pool.py：完整原版解码、完整SHA/大小、四封存和只读FD复用；原型broker的peer准入及权限必须按账号隔离重新审查。分发体、共享映像、worker及控制内存分别记账。
- 原型响应来源包括原始Gemini帧和派生视图。正式业务载荷保真、非流式聚合、终态、usage和错误必须分别验收。

## 下游真实兼容差异

- /root/project/new-api/relaykit/relayconvert/internal/oai_chat/to_gemini_chat_req.go:20-32：转换会保留temperature、topP、maxOutputTokens及seed，后续还有stopSequences和thinkingConfig。
- /root/project/new-api/relaykit/dto/gemini.go:330起：GenerationConfig定义更广的Gemini参数。new-api源码和渠道配置处于本任务外部范围，本轮只读核对。
- 原型对这些生成参数大多直接拒绝。先前参数矩阵还记录部分Cortex配置未出现在实际出站，因此只接受JSON字段不代表参数生效。
- 官方协议参考：https://ai.google.dev/api/generate-content?hl=en 。公开generateContent与streamGenerateContent的请求/响应合同为接线参考，不代表AGY原生已完整支持。

## 用户已决定的参数兼容

用户说明temperature、topP当前基本不发送，并要求这些字段保持兼容。首期明确接收并忽略这两个字段，沿原生默认值执行；maxOutputTokens继续采用真实映射。记录中的接收字段与实际生效字段分别表达。其他工具、模型及结构能力按实际支持校验。该决定覆盖本轮参数取舍，规划无剩余产品问题。
