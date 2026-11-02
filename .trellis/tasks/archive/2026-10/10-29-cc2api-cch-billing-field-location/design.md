# F01 技术设计

## 边界与依据

- 产品修改集中于 `cc2api/src/service/rewriter.rs`；Gateway 继续通过既有 `Rewriter::refresh_cch_attestation` 刷新重试正文，不改变其调用顺序和账号／客户端门禁。
- [PRD](./prd.md)定义行为；[第一轮评审](../10-29-cc2api-vm2api-wire-differential-study/research/alignment-review/round-01.md)提供冻结反例。研究原件保留，新验证单独记录。
- 复用已有 `find_top_level_field_value_range`、`find_top_level_field_ranges`、`scan_json_string_end`、`scan_json_value_end` 及空白处理，不新增解析依赖或通用递归框架。

## 定位与数据流

1. 读取根级 `system` 原始范围；数组只检查直接 text block 的 `text`，字符串形状检查已有 billing attribution 行。
2. 识别完整 `x-anthropic-billing-header:` 行和独立 `cch=<5hex>` 字段。兼容既有入口标签与附加归因键，不要求恰好三个字段或固定字段顺序；保持原始字节，不直接采用 classifier 专用的严格 `cli`／仅两个键限制。
3. 只更新唯一合法 billing 中的唯一合法 CCH；缺失、非法、重复或无法可靠映射到原始字节的目标返回无目标，不搜索 messages、tools、metadata 或其它嵌套字段。
4. 初始占位化限定于受管理的根级 billing，移除通用文本／reminder 对任意 CCH 的重置；沿用现有 cache_control 跳过条件。
5. 初始封口与刷新共享原始字节定位。初始封口仍处理受管理占位值；刷新只把目标五位值归零，再复用现有版本投影、seed 与 xxhash64 计算并回填。

## 字节与兼容契约

- `cch_attestation_input` 的精确版本投影不变，保留 169／172／173／257／260／280／293 与未知版本回退规则。
- 不用 JSON 往返构建哈希输入；局部识别所需解码不改变发送字节。区分解码字符串偏移与原始 JSON 字节偏移，不能直接相加。
- 五位 CCH 外的原始字节保持，包括字段顺序、空白、Unicode 与转义。编码无法可靠定位时跳过，不做猜测性修改。
- Rewrite／Strip 与 API mimicry 门禁仍由原调用方掌握；不新增 setting、DB 字段、身份或画像。
- 重复 billing 的合并／拒绝和 cache_control 合法性留给 F04；本任务只令歧义 CCH 定位不写入，不宣称请求已被规范化。
- 首轮 `cc-body-billing-extra` 已证明附加归因键属于既有透传范围；F01 不能因为收窄目标搜索而令其失去封口能力。用户本轮选择 F04 不调整，仍保留这些字段和键序；该兼容修正不扩大为字段清理或入口统一。

## 风险与控制

- 只修最终封口仍会遗留前置重置污染；必须覆盖前置重置、封口与公开刷新。
- 转义、相似前缀、超长值和重复字段可能误定位；用原始字节负例及差异范围断言验证。
- classifier 特殊路径会补齐或刷新 billing，缓存改写位于封口之前；保留已有回归并加入干扰 CCH。
- 保守跳过歧义目标可能保留占位值，这是本任务避免猜测写入的边界；异常请求策略后续评审。

## 回滚

不涉及数据迁移或外部状态。必要时只回滚本任务的 rewriter、测试与对应 CCH spec 改动，保留已交付 UTF-16 修复和研究原件。
