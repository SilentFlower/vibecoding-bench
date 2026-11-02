# beta 请求规范化设计

## 边界与交接

本任务对应 R3-02／04。现有提取与 URL 构造集中在 `cc2api/src/service/gateway.rs`；只改变 beta 的多值收集和目标路径的 beta query。基线包括已推送 R2-01 及尚待交接的 R2-03／06，本任务实施必须等待共享 Gateway 文件交接。

现有 `merge_anthropic_beta(required: &str, incoming: &str) -> String` 已由 Gateway 导入，可复用其逗号拆分、trim、精确去重与首次出现顺序。无需修改 Rewriter 的画像、账号能力或 CCH 算法，也无需新增依赖、配置、迁移或管理页面。

## 请求头数据流

1. 保持 `extract_headers(&HeaderMap)` 原有其它头的取值及非法字符串跳过行为。
2. 仅对 `anthropic-beta` 使用 `get_all(...).iter()` 按同名值插入顺序收集；每个可转字符串的值通过既有合并函数折叠。
3. 有有效但为空的 beta 仍保留“头存在”的语义；全部无法转字符串则与既有行为一样跳过。头名按 HeaderMap 本来支持的大小写规则处理，token 仍精确匹配。
4. 普通请求与 count_tokens 继续共享提取入口，随后分别进入既有账号 1M／Fast 过滤和画像合并。现有已知 token 位置、293 safeguard／title／后台窄表与 API 生成策略保持原合同。

不会将 UA、request-id、Authorization 等单值语义的头机械拼成逗号列表。测试中需先移除 `profile_request` 自动添加的 beta，再用 `HeaderMap::append` 构造真实重复值。

## URL 数据流

仅 `requires_upstream_beta_query` 已命中的精确路径生效：按 `&` 保留原始片段，只对每片段 `=` 前的键做一次百分号解码比较；精确小写键 `beta` 的首次出现输出 `beta=true`，后续同名片段删除。不存在时末尾追加。编码后的同名键同样归一，畸形编码或其它键按原片段保留，不执行递归解码。

其它片段的值、百分号大小写、空片段、顺序与重复值不经整条 URL 的解析再序列化。非目标端点沿用原 query；`count_tokens_upstream_url_with_base` 专用固定 `?beta=true` 的合同不变。无需将研究用 `synthetic_client_id` 加入黑名单，也不建立只允许 beta 的白名单。

## 证据、取舍与兼容性

592 条已读取原生 Messages 均只有唯一 `beta=true`；280 七份 `.flow` 原件与 JSONL 复核一致。293 的本地报告不含完整 query，既有远端目标连接超时，原件未读；不能把 280 或裸路径报告当作 293 原始 URL 证据。

本修复只消除已确认的 beta 冲突。未观察到其它 query 不能证明官方未来扩展或第三方合法参数应被删除，因此保留未知片段。重复 beta 的 token 集合应不再受两行先后影响；未知 token 的相对顺序仍遵循已有合并合同，不承诺任意交换后最终字节完全相同。

## 验证与回滚

实际 Gateway＋本地 loopback 同时观察最终头和 URL，不能只测中间 HashMap。覆盖 280／293、账号允许／禁止 1M、Fast、重复值交换、重叠空段、头名大小写、相似日期、293 特殊画像、API 和 count_tokens。URL 覆盖缺省／空／false／重复混合／编码同名键、畸形或双重编码键、其它参数编码及重复保真和非目标路径。

交接后重跑受影响的 R2 清理／Session、stream 和 CCH 回归，执行 Rust 格式与全量测试。无前端源码变化时复用 R2 已有效的前端构建证据。

回滚只恢复此次 beta 收集和 URL 归一逻辑及关联测试，保留 R2、旧画像和账号能力过滤；不涉及数据库回滚或远端操作。
