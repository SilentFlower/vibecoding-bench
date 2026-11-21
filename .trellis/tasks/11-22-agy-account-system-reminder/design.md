# 账号级 Messages 提示词位置设计

## 账号配置

在 `Account` 增加布尔字段 `agy_system_prompt_as_user_reminder`。复用 `Accounts.vue` 的 Antigravity 配置和差异提交。新建、编辑、表单重置、旧账号回读使用相同默认值。创建账号的请求类型、`update_agy_fields_locked` 和 `AccountStore` 分别沿当前账号选项合同处理该字段。管理更新只提交显式字段，推理按实际选中的账号取值。

SQLite 用冻结登记后的第 10 步追加 `INTEGER NOT NULL DEFAULT 0`。同一迁移支持 PostgreSQL 初始化路径。登记迁移源码、校验和、平台签发源映射及回退兼容声明。现有 1–9 步沿各自已登记定义验证。按单账号保存选项时复用现有状态与配置门禁。

## 请求投影

`gemini/messages.rs::convert_request` 先完成现有 Messages 解码、当轮补充文本映射及本地摘要识别。为已选账号准备普通 Messages 模型生成时，在冻结的 `AgySystemPromptPolicy` 附上可选的 `user_reminder_index`。位置取第一条没有函数回填的用户消息。空白系统文本、缺少普通用户段、WebSearch 和本地摘要沿既有表示。

原生适配器按现有方式合并 `systemInstruction.parts`，调用同一个 `transform_system`。有提醒位置时，将转换后的文本包装为 `<system-reminder>`，追加至受信索引所指用户段的末尾。系统段使用 `Use the provided context to answer the user's request.`。转换回执以 `cortex_user_reminder` 标记实际落点，原有系统段来源继续使用 `cortex_custom_system`。网关和采集读取核对已知来源。保留原始正文与原有用户 part 的顺序、文本、图片、签名及工具字段。

## 工具续轮与恢复

`gemini_body` 保留提醒投影前的私有正文。领取时继续按此正文核对原工具归属，使用既有原生 ID 和签名修正。已提交轮次持有自己组装后的文本，后续配置变更只用于新生成。历史路径在确认旧轮退出后按现有归属继续生成。

新一轮生成在现有准入后读取当前账号配置，每次按本轮策略在原生构造请求时投影一次。已有回执继续持有单次提交权。`drive` 在 OAuth 恢复复用首次冻结的策略。禁用位置时省略私有索引，沿旧版信封。启用此项需要网关、发送器和原生适配器支持该索引和回执来源。旧严格消费者拒绝未知启用策略。

## 回退

保存关闭后，后续模型生成使用独立系统段。已交付的工具批次保留自己的旧提醒视图，仍可按原归属收口。一次试验使用两组独立新会话，避免把旧会话的缓存前缀差异计入试验变量。
