# 套餐适配设计

## 数据与入口

1. Account 和 DeviceProfile 新增可空 rate_limit_tier；数据库幂等增加 TEXT 列并同步 SQLx Any 的创建、读取、更新及测试构造器。
2. 管理创建/更新 DTO、web api.ts/账号表单同步字段，输入修剪且校验长度与控制字符；缺字段不覆盖，显式空值按接口合同清除。账号数据中不新增推断的原始 subscription_type。
3. `_read_bench_profile_identity` 从 claudeAiOauth.rateLimitTier 读取真实值，创建、显式同步及现有重授权保存透传。元数据局部写入不得整行覆盖并发轮换的 AT/RT。
4. 若重授权 DTO 携带可选套餐元数据，纳入已存在的导入事务与请求摘要；新可选字段未提供时序列化省略，保证旧导入回执的重复请求仍匹配。原租约、内部服务证明和凭据条件写入保持。

## 规则与兼容

- 展示规则仅使用原始类型和真实分级：ultra → Ultra；max/default_claude_max_20x → Ultra；max/default_claude_max_5x → Max；单独 max → Max；其他已知类型保持；冲突/未知分级不猜。
- Rust 遥测与 GrowthBook 改写复用一个分级选择函数，显式真实分级优先。原有旧账号兼容回退不得作为展示证据；ultra 缺真实分级时不生成未验证的新分级字符串。
- v3 Vue 使用同一合同的展示辅助函数；ai-fund 仅在 BFF 白名单内归一化为展示套餐，前端增加 Ultra 文案。跨语言用同一场景矩阵验证，避免仅改其中一条路径。
- 旧源没有真实分级字段时仍显示 generic Max，不把遥测默认 20x 或用量多少当证据。

## 额度窗口

保持 OAuth usage 返回中显式 null 的语义，以及缺失/异常的未知语义。页面可显示“当前未返回 5 小时窗口”与“用量未知”，不能仅凭 Ultra 名称或 null 推导无限制/已验证。存在真实窗口时继续计算实际百分比、闸线和重置时间。后端既有真实窗口判定继续使用有效数字与未来重置时间，不引入套餐名放行规则，不改固定窗口外的主动探测策略。

## 来源退役能力

claudeEnv 沿用 vm2api 的显式停用模式，识别每个前缀的 ENABLED=0/false；未设置时兼容现有 base/token 启用逻辑。所有来源显式停用时不能把原来源作为故障占位重新加入；全未配置的既有诊断仍保留。源关闭后分页预算、来源缓存和聚合使用实际已启用来源；cc2api-2 身份不改名。

## 影响文件

cc2api：model/account.rs、model/identity.rs、store/db.rs、store/account_store.rs、service/account.rs、service/telemetry.rs、service/rewriter.rs、handler/router.rs、对应测试与 web 的 api.ts/Accounts.vue/辅助函数。
bench：orchestrator/main.py 的 profile 同步与重授权载荷、对应既有 Python 测试。
ai-fund：worker/src/pools.js、对应号池测试、frontend/src/views/Pools.vue 和 pools-sources.spec.js。配置的实际退役值归第三子任务。

## 验证和发布

Rust 完整测试与 fmt、相关 Python unittest、两前端构建、ai-fund pools 系列测试及页面组件验证。v3 以同批 control/account 镜像发布，部署 us 时沿用不备份/不重算内存的已确认选择。ai-fund 只发布现有主版 Worker ai-hub 与 Pages ai-hub-all/main，保留现有 CloudFront 域名、回源与授权配置；不发布 biz 分支，不迁 D1。
