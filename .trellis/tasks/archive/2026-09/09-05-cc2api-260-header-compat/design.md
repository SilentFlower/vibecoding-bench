# 技术设计

## 版本画像与改写

- `RequestProfile` 增加标题可选 beta 列表，257/260 声明两个 token，旧画像为空。
- `EndpointProfile` 增加后台请求头画像枚举，避免从版本字符串推导能力。
- 复用 Haiku classifier；输出前按可选白名单重建标题 beta，保留窄画像顺序。
- 后台端点严格匹配路径段，统一在 header 改写后规范化 UA/beta，覆盖两种入口。
- 不处理 Authorization 或 body/CCH；未知路径和旧画像保留既有逻辑。
- 本轮只修复 UA/beta 组合，不宣称 HTTP wire 顺序或完整 worker 协议对齐。

## 待讨论方案

worker JWT 当前仍在 `gateway.rs` 的普通上游令牌解析/注入分支被账号令牌替换。本轮仅修 UA/beta；完整 worker 代理建议使用以下独立链路：

1. bridge 请求按现有网关 token 鉴权、选择账号；仅从成功且可信的上游 bridge 响应登记 worker JWT，关联调用者、账号、session、worker_epoch、expires_in。
2. 若客户端后续直接以 worker JWT 调用网关，认证必须命中已登记凭据的摘要及绑定关系，只授权指定 worker 路径和 session。不能仅判断 Bearer 看起来像 JWT 就放行，也不能允许它调用普通 messages 或管理端点。
3. worker 请求使用该 JWT，固定原账号和出口；不再走账号 access/setup token 替换或普通池换号。过期、epoch 变更和 session 结束时失效，通过 bridge 重新建立；worker 凭据失效不能直接按账号永久失效处理。
4. bridge 的 api_base_url 在抓包中指向官方服务。若完整接管代理，还需改写这个地址并验证客户端实际路由，以及 events stream 的取消、断线和重连；仅透传 Authorization 不能解决整条链路。

API 模式当前只接管部分模型/thinking/system 字段，缺少这些字段时不会补充 context_management/diagnostics/global scope。建议分开落地：

- context_management：仅在目标模型与 thinking 模式兼容、调用者未显式设置时，补入抓包中的 `edits=[{type:"clear_thinking_20251015",keep:"all"}]`；probe/title/thinking disabled 单独保持适用边界。
- diagnostics：从 SSE `message_start` 或非流式响应记录真实 message ID；用调用者、账号、真实会话与历史前缀/分支绑定。下一轮只有确认历史连续时填写 previous_message_id；首轮、换号、截断或并发分支无法确认时省略，不能随机生成或复用该账号最近一次请求的 ID。
- global cache：仅将版本化、稳定、无用户数据的公共 system 前缀放入 `scope:"global"` 的缓存块；用户 system、路径、环境和私有工具信息不得进入这个公共块。同步处理现有断点预算和 TTL，最后统一排列 body 并重算 CCH。

以上为建议方案，尚未实现；diagnostics 所需的真实会话识别不能直接假定已有 API session hash 足以区分所有对话分支。

## 验证与回滚

人工 fixture 仅含协议常量、合成路径。覆盖已知/相似未知路径、两种当前版本和旧回滚版本。无设置或 DB 迁移，代码回退即可恢复。

## 推送与部署

用户于 2026-09-05 明确要求推送并部署。先推送 cc2api 三个修复文件，触发既有 CI Docker；父仓同步 gitlink 和协议规范。等待 CI 构建对应提交的 SHA 镜像，核对远程现有 Compose、数据卷和服务，备份配置与 SQLite 后在低连接窗口 recreate cc2api。部署后核验 revision、容器状态、HTTP、DB 完整性及设置摘要，最终提交任务记录；不部署 bench，不进行主动模型测试。
