# F01 实施验证

日期：2026-10-29。产品基线：`d5749d923e997fd3c01dde31248b5af8dde906ee`。本轮只使用合成正文和本地测试；完整日志位于 `/tmp/cc2api-f01-validation/`。

## 修复前失败复现

先添加三项回归，再运行 `cd cc2api && cargo test --locked cch_ -- --nocapture`，退出码 `101`：21 项通过、3 项失败，日志 `before.log`。

| 回归 | 基线观察 |
| --- | --- |
| `cch_initial_seal_preserves_user_placeholder_before_billing` | 用户示例 `cch=00000` 被首次封口修改 |
| `cch_retry_refresh_preserves_user_hex_before_billing` | 用户示例 `cch=12345` 被公开刷新修改 |
| `cch_placeholder_reset_preserves_system_document_and_reminder` | 普通 system 文档的 `cch=12345` 被前置重置为 `00000` |

前置修复后的首次定向运行 `after-initial.log` 中，三项回归及既有 CCH 测试通过。

## 独立字节参考

系统 `libxxhash.so.0` 的 `XXH64` 经 Python `ctypes` 调用复算。脚本 `/tmp/cc2api-f01-validation/reference.py` 对每组固定合成正文使用显式字节片段投影，用唯一入口标记确定目标，未调用产品定位、投影或 hash 函数。原始摘要记录在 `reference.jsonl`，独立期望已固定于 `cc2api/tests/fixtures/cch-billing-location.json`。

| 合成场景 | 版本 | 正文字节／投影字节 | 五位值起始偏移 | 独立 xxhash64 | CCH |
| --- | --- | --- | --- | --- | --- |
| 用户／工具／metadata 在 billing 之前，含嵌套 system | 293 | 649／593 | 558 | `c79c53984e058913` | `58913` |
| system 字符串在前，前缀／空白／中文／转义 | 280 | 290／247 | 108 | `8abca525fb49ada6` | `9ada6` |
| system 数组在后，块附加键与字段顺序 | 169 | 248／248 | 206 | `72e1b531d74d33b5` | `d33b5` |
| 未知版本保留全正文与 legacy seed | 2.1.999 | 219／219 | 160 | `2f546a7e02b37291` | `37291` |
| 完整 CC 改写，用户／工具抢先 | 293 | 264／229 | 170 | `8b5a3ef310f0eab6` | `0eab6` |
| CHK-001：CCH 后保留附加 billing 字段 | 293 | 157／157 | 109 | `b057ccc826d32214` | `32214` |

293 正文 SHA256 为 `fba3f787849bfbcf83ed729530cb230bd509f48ed2936d8008000ec8b16cf8e1`，投影 SHA256 为 `ec8972999348e215519ffb897fa0c89c19bed46e46938c2527e1294cdd0468c6`。其它摘要保存在合成夹具与参考日志中。

`cch_billing_location_matches_independent_reference_and_exact_bytes` 同时检查首次封口、将指定目标设为 `A1b2C` 后刷新、重复刷新幂等；预期输出只在独立记录的五个字节内回填固定期望，因此会检测其它字节的重排或改写。

第五组还使用实际 `Rewriter::rewrite_body` 完整改写入口，输入与最终合成字节均由独立脚本固定。脚本独立计算 ASCII 样本的 `cc_version` SHA256 后缀、受管理 CCH 归零与版本投影，再由系统 XXH64 得到期望。最终正文 SHA256 为 `b37781f5b0ed10c309094f6e01b9e877d64e824267b76c733df656fa48f4be70`，投影 SHA256 为 `e69470299c6adf8dfe61c587ea1a25c525c6a022d23e6c50db1713b45ca1445f`。

## 覆盖边界

- 根级字符串／数组 text block，system 在前／后，块附加键、JSON 字段顺序和空白；兼容 `cli/sdk/subagent/custom` 标签。
- 用户／工具定义与结果／metadata／reminder／普通 system 文档／嵌套 system 示例；正文同时包含占位值和非零值。
- CCH 缺失、长度／字符／边界非法、重复 CCH／billing、重复 JSON `system/type/text`（含转义 key）；无法直接回填五位值的转义编码保守跳过。
- 完整 API／CC 两类入口与实际 `Rewrite/Strip` 两种枚举值，缓存 off/auto、classifier 新增／已有 billing、公开刷新门禁及重试刷新。
- 前置占位化仍按 `cache_control` 键存在即跳过，包括 null；重复 billing 只令 CCH 不写入。
- 既有 169／172／173／257／260／280／293、UTF-16 后缀、缓存封口和 Gateway 签名重试回归继续参与检查。

## 首次实现验证

- `cargo fmt --check`：通过，日志 `fmt.log`。
- `cargo test --locked cch`：35 项通过、0 失败，含完整改写独立参考，日志 `cch.log`。
- `cargo test --locked`：退出码 `0`，689 项通过、0 失败、3 项既有 PostgreSQL 外部库用例按默认配置忽略，日志 `full.log`。
- `git -C cc2api diff --check`：通过。

三个默认忽略项为 diagnostics、usage limits、profile settings 的独立 PostgreSQL 存储验证；本轮无数据库改动。

扩大回归开发过程中修正过两项测试问题：误用了实际枚举不存在的 `Passthrough`，以及 API 注入原 system 后仍按 `messages[0]` 查找原用户消息。两项均修正测试，未扩展产品行为；开发日志分别为 `cch-development.log`、`cch-development-2.log` 和 `full-rewrite-debug.log`。

## CHK-001：billing 附加字段兼容修正

主会话 Check-All 发现新建三字段正则会令首轮研究 `cc-body-billing-extra` 回退：原输入在 CCH 后具有 `cc_prompt_id=synthetic; cc_is_subagent=true; synthetic_fingerprint=synthetic-canary;`，基线保留这些键并正确封口为 `9e5d1`，首次 F01 实现却因额外字段跳过 CCH。用户本轮明确 F04 不调整；保留这些既有字段属于 F01 的兼容约束。

先补回归，再运行 `cargo test --locked cch -- --nocapture`：退出码 `101`，34 项通过、2 项失败，日志 `chk-001-before.log`。失败项为 `cch_billing_extra_fields_and_field_order_preserve_existing_compatibility` 和增加第六组独立期望后的 `cch_billing_location_matches_independent_reference_and_exact_bytes`。

删除三字段／固定顺序正则后，按分号分隔的独立字段定位唯一 `cch`。保留 billing 首行与已有版本／入口识别信号，额外字段保持原文和顺序；`note=cch=12345`、`xcch=fedcb` 只作为未知字段值，不作为 CCH。无值、非法长度／字符／边界和重复 CCH 仍停止写入。没有新增字段清理、顺序整理、缓存标记处理或入口策略。

新增回归分别覆盖研究实际结构、CCH 前后附加键、CCH 位于首字段、版本／入口／CCH 变序和空白，以及字符串／数组 system。每组同时验证前置重置、首次封口、刷新和完整 CC `rewrite_body`；通过受管理的线程后缀复用保持其它字节稳定。独立最小样本正文／投影 SHA256 均为 `ff815a084208b83820772e50dc923778b9f002d032f9ff7f46b6c2b8710d9812`，系统 XXH64 为 `b057ccc826d32214`，CCH 为 `32214`。

最终复验全部退出 `0`：`cargo fmt --check` 通过（`chk-001-fmt.log`）；`cargo test --locked cch` 为 36 项通过、0 失败（`chk-001-cch.log`）；全量 `cargo test --locked` 为 690 项通过、0 失败、3 项既有 PostgreSQL 外部库用例默认忽略（`chk-001-full.log`）；`git -C cc2api diff --check` 通过。

最终验证文件 SHA256：`rewriter.rs` 为 `01a80e8fa68bae3f6a78a80fde6d9807ad782ba02d754ba7db84e97dbcbf2540`，`cch-billing-location.json` 为 `81d5bbae362f31ee13f0ab4ccd2fe23baebef7ecb48e9379b126ef5db2afe78f`。

## 交接与限制

受管理 billing 定义为根级 system 字符串或直接 text block 的首个非空白位置具有完整 attribution 行，可跟多行普通上下文；普通文档中后续引用不作为目标。既有 builder／260、280、293 夹具与缓存回归符合此形状。

歧义目标可能保留原值或占位值；缓存标记合法性与重复 billing 规范化按用户决定，本轮保留现状。Check-All、Spec、实际 Git 计划、完成状态与 Close 由主会话继续处理。
