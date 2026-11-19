# Claude 会话策略封禁设计

## 边界与总体流程

1. 已鉴权消息在解码并解析原始 body 后冻结会话身份。运行期开关在检查时读取，时长在实际拒答识别时冻结。
2. 以独立固定命名空间、Token ID（无 API Token 时沿用现有默认域 0）、改写前 SID 计算 SHA256；数据库和管理 API 只保留该匿名身份。身份缺失时保持原入口行为。
3. 在调度、账号选择、Hello 探测和遥测激活之前查询有效封禁，命中直接返回本地错误。
4. 排队后以及实际传输提交前复查，覆盖原生作业提交、Rust 请求、签名修复和 OAuth 重试。
5. 实际响应由与诊断开关独立的有界观察器解析；识别明确策略拒答后原子创建一轮封禁。原始响应按既有协议继续交付。
6. 后续本地拦截累计次数和最近命中时间，固定该轮到期时间；时间到期后恢复正常处理。再次上游拒答开启下一轮记录。

## 新增数据模型与存储

新增独立 `model/session_policy_block.rs`、`store/session_policy_block_store.rs` 与 `service/session_policy_block.rs`，类型和方法在实现时依实际调用点确定。

持久表 `session_policy_blocks` 每行表示一轮封禁：

- `id`：UUID 主键，供管理操作引用。
- `session_key`：上述域分隔 SHA256；会话原文不落库。
- `api_token_id`：调用方令牌 ID；令牌名称以管理查询安全投影显示。
- `account_id`、`model`：触发时的账号 ID 和模型；来源只取已有可信调用上下文。
- `reason`：白名单策略原因枚举；原始错误正文和用户正文不入表。
- `source_request_id`：可选诊断关联，日志关闭时保持空值。
- `blocked_at_ms`、`expires_at_ms`：服务端 UTC 毫秒时间戳。
- `released_at_ms`：可选手动解除时间。
- `blocked_request_count`、`last_blocked_at_ms`：后续本地拦截摘要。

索引覆盖会话有效状态查询、开始时间倒序分页；事务锁定同一会话的状态写入，保证同一有效轮次的并发拒答合并、解除幂等和新轮次边界。必要的锁定行属于同一迁移定义；不得用每进程内存锁替代跨连接约束。

SQLite 添加第 4 步 `gateway.session-policy-blocks.4`，纯定义置于 `session_policy_block_schema.rs`；同步登记摘要、版本执行与结构校验、发行来源映射。PostgreSQL 在既有初始化路径应用同等增量结构。既有 baseline、proxies、proxy-sync 定义保持冻结。时间整数读取沿 AnyPool 兼容合同使用严格文本解析，分页依数值排序。

## 配置

- `session_policy_block_enabled`：字符串布尔，默认 `true`。
- `session_policy_block_duration_minutes`：正整数字符串，默认 `1440`。只接受可安全转成毫秒并加到当前时间戳的数值，拒绝空值、零、负数、小数、非法文本及溢出。
- 配置在设置 API 整体校验后事务保存、原子热刷新。自动封禁持续时间以首次识别时冻结的配置计算，已有有效轮次保持原时间。
- 关闭功能停止新封禁与拦截；已有历史保留，重新开启后尚未到期记录继续有效。
- Settings 元数据在“会话与调度”分类新增“会话策略封禁”段，输入单位为分钟，帮助文案明确默认 1440 分钟等于 24 小时，并提供管理列表入口。

## 拒答识别与响应观察

- 仅解析实际响应的结构化错误、SSE `error` 事件、`stop_reason=refusal` 及明确 refusal 内容块。
- 文案匹配限定于错误对象；支持 Usage Policy / `legal/aup`、截图的 safeguards flagged 与 reasoning_extraction，以及现有常见内容策略错误码。正常 assistant 文本引用这些词保持正常行为。
- 普通 HTTP 错误识别发生在账号故障处理与可修复错误重试之前；明确策略拒答停止账号迁移与修复重试。
- 复用现有响应解码和增量解析能力，新增有限原因状态。观察器不改写正常流字节，不整段缓冲长流；事件与解压上限沿既有合同。
- HTTP 200 SSE 中观察到拒答事件时立即等待封禁写入，再交付当前片段；避免依赖流结束、后台落盘或诊断开启。
- 存储读写错误返回明确的本地临时故障或记录实际封禁写入失败；后续状态查询失败返回 503。失败处理不得宣称封禁成功。

## 本地错误合同

有效封禁返回 HTTP 400 的 Anthropic error object，`error.type=invalid_request_error`、`error.code=session_policy_blocked`，说明当前会话被限时封禁。附带 `retryable=false`、`expires_at` 与剩余秒数，避免自动重试或登录误导。会话原 ID 保持私有。新拒答的原始上游状态与字节保留。

count_tokens 只查询已有封禁，命中使用同一错误合同，保持计数路径的独立准入与计费语义。历史已发出的后台遥测和已提交的并发调用沿原生命周期结束。

## 管理 API 与界面

- `GET /admin/session-policy-blocks`：管理员鉴权，支持 `state=all|active|expired|released`、`session_prefix`、`page`、`page_size`；默认 20，沿公共分页提供 10/20/50/100，最大 100。
- 返回 `items/total/page/page_size/observed_at_ms`，附带安全投影。状态根据服务器当前时间与解除字段推导；列表读取不更新封禁。
- `POST /admin/session-policy-blocks/:id/release`：明确解除单轮封禁，原子写入解除时间；重复操作保持幂等，历史保留。
- 前端新增 dashboard 子页 `/session-blocks`“会话封禁”，加入网关导航的“请求记录”下方。页面顶部提供“封禁设置”直达对应设置分区。默认显示封禁中，可切换全部与历史状态；查询条件变化重置页码。
- 表格显示匿名会话、访问令牌、触发账号、模型、原因、开始/到期时间、状态、拦截次数、诊断入口和解除操作。
- 桌面与 390px 复用已有视觉 token、分页与控件；时间调用统一 `formatLocalTime`。解除使用共享确认和操作反馈；失败保留当前数据，明确陈旧状态，离页取消读取并丢弃迟到回执。

## 风险与兼容性

- 并发窗口：标记前已提交的调用可能继续完成；标记后新请求与已排队未提交请求都复查有效封禁。
- 误判：只认结构化拒答证据，保持认证、限流、参数错误及普通正文为独立分类；管理员可提前解除。
- 数据库故障会使封禁状态未知请求收到 503，这是为满足本地拦截承诺采取的保守策略。
- 原生与Rust分支、普通与SSE响应、info日志模式均需独立覆盖。封禁作用域在上游 session 池改写之前冻结。
- 结构变更为兼容新增。功能开关可停止拦截；旧程序可继续读取旧表，记录保留供后续启用。
