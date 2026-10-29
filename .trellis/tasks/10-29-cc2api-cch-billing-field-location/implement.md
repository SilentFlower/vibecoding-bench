# F01 实施计划

## 实施前提

- 用户已完整评审 [Brief](./brief.md) 并批准交由 subagent 实施；主会话已运行 `task.py start`，任务为 `in_progress`，实施路由为 `subagent`。
- 实施前按 `trellis-before-dev` 加载本任务材料和 cc2api backend／protocol 规范；沿用当前分支，保留创建任务前记录的其它 dirty 文件。
- 本任务仅交付 F01，不改原研究矩阵，不顺带实现 F03／F04／F05。

## 执行顺序

- [x] 添加能稳定失败的合成回归：初始用户 `cch=00000` 抢先、刷新时非零 CCH 抢先，以及 reminder／普通 system 示例被前置重置。
- [x] 实现唯一根级 billing CCH 定位；复用现有扫描，覆盖 system 字符串／数组、字段顺序、转义及非法／重复目标。
- [x] 收窄前置占位化，使封口／刷新共享定位；保持版本投影、门禁与 cache_control 跳过规则。
- [x] 从现有账号／画像测试定义构造 API、CC、classifier 特殊路径和公开刷新回归，验证真正 billing 与其它字节。
- [x] 用独立 xxhash 参考复算至少一组含干扰 CCH 的最终合成字节，记录输入摘要、目标位置与结果，不调用产品定位函数生成预期值。
- [x] 修正 Check-All `CHK-001`：保留 billing 附加键及原有字段顺序，按独立字段识别唯一合法 CCH；补充研究真实结构、变序、前后附加键及独立 `32214` 回归。
- [x] 运行下方检查并记录；失败先在本任务范围修复，未通过不宣称完成。`CHK-001` 修正后格式、全量与 CCH 定向均通过，见 [validation.md](./validation.md)。
- [x] 进入 `trellis-route(target=check)` 的 Check-All；附加 billing 字段兼容修正复核通过，Spec 已更新，精确文件 Push 计划已准备。
- [x] 用户已确认本次精确 Git 计划，两个业务仓库已提交并推送；本批任务记录包含最终进度与 Close。

## 验证命令

在 `cc2api/` 执行：

```bash
cargo fmt --check
cargo test --locked
cargo test --locked cch
```

新增回归先定向运行以保存修复前失败证据。最终通过后，只在新变更或失败需要时重复检查。不涉及前端／部署，不运行无关构建或真实模型请求。

## 验收映射

| 验收 | 验证内容 |
| --- | --- |
| AC1 | 原 F01 两类反例、独立参考与真正 billing |
| AC2 | 用户／工具／metadata／reminder／system 文档／嵌套 system 保护 |
| AC3 | 字符串／数组、中文／转义／空白／字段顺序、五位之外字节不变 |
| AC4 | 缺失／非法／重复目标不回退全文搜索 |
| AC5 | 历史夹具、API／CC 模式、classifier／缓存／重试及跳过条件 |
| AC6 | 格式、全量、CCH 定向与 Check-All 记录 |

## 高风险位置与回滚点

- `src/service/rewriter.rs:2317`：system／reminder 共用闭包；收窄 CCH 时不改变其它环境改写。
- `src/service/rewriter.rs:2569` 至 `2633`：封口与刷新；保持版本投影及最终字节。
- `src/service/rewriter.rs:2813` 起：共享 JSON 扫描器；优先复用，若必须改公共扫描语义，先补测试并核对所有调用方。
- `src/service/gateway.rs:2572`：只核对重试调用，不预设修改 Gateway 生产逻辑。
- 回滚只覆盖本任务实际 diff，保留 `d5749d9`、研究原件及任务创建前 dirty 基线。
