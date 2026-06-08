# cc2api cache_control TTL 改写设置设计

## Technical Design

### 设置契约

- 设置 key: `cache_control_ttl_rewrite`。
- 默认值: `off`。
- 合法值: `off`、`5m`、`1h`。
- 存储位置:沿用现有 `settings` 表 key-value 存储。
- 读取方式:网关服务启动时从 `SettingsStore` 加载到内存 `RwLock`,设置更新后调用 reload 方法刷新。

### 后端边界

- `src/store/settings_store.rs`
  - 新增默认值常量,供数据库默认插入、接口默认补齐和网关 reload 复用。
- `src/store/db.rs`
  - 默认 settings 插入列表新增 `cache_control_ttl_rewrite`。
- `src/handler/router.rs`
  - `get_settings` 对旧库补齐默认值。
  - `update_settings` 校验枚举值,并在该 key 更新后刷新网关内存配置。
- `src/service/gateway.rs`
  - 在 `GatewayService` 上新增 TTL 改写配置缓存。
  - 请求转发时与 `EnvPassthrough` 一样只读取内存状态,不在热路径查库。
- `src/service/rewriter.rs`
  - `rewrite_body` 增加 TTL 改写参数。
  - 在 `/v1/messages` body 完成现有改写后、序列化和 CCH attestation 计算前执行 TTL 改写。
  - 改写函数只遍历顶层、`system[]`、`messages[].content[]`、`tools[]` 的已有 `cache_control`。

### 前端边界

- `web/src/components/Settings.vue`
  - 新增本地状态 `cacheControlTtlRewrite`。
  - `loadSettings` 读取缺省值 `off`。
  - `saveSettings` 提交该设置。
  - 在现有系统设置 UI 中增加三选一控件,文案明确 “不改写 / 强制 5m / 强制 1h”。

### 行为细节

- 当设置为 `off` 时,不调用 TTL 改写逻辑。
- 当设置为 `5m` 或 `1h` 时:
  - 遇到已有 `{"cache_control":{"type":"ephemeral"}}` 时补 `ttl`。
  - 遇到已有 `{"cache_control":{"type":"ephemeral","ttl":"..."}}` 时覆盖 `ttl`。
  - 遇到没有 `cache_control` 的 block/tool 时跳过。
  - 遇到 `type` 不是 `ephemeral` 时跳过。
- API 客户端分支目前会剥离 system/messages 内容块的 `cache_control`;本任务不改变该剥离策略。若后续需要针对 API 模式保留缓存断点,应另开任务。

## Rollout / Rollback

- 默认值为 `off`,上线后不改变既有请求行为。
- 如开启后发现缓存行为异常,在设置页改回 `off` 即可停止后续请求的 TTL 改写,无需重启。
- 数据库仅新增 key-value 默认项,无 schema 迁移和破坏性变更。
