# 实施计划

- [x] 核对抓包、画像结构、入口和现有测试。
- [x] 补充版本化标题 beta 与后台 header 画像。
- [x] 修复并增加脱敏 fixture、回归测试。
- [x] 执行格式、定向、CCH 与全量 Rust 测试。
- [x] 执行 Check-All 并更新协议规范。
- [x] 汇报修复范围及 worker JWT/API 方案。
- [x] 按追加授权推送 cc2api 修复与父仓 gitlink/规范。
- [x] 等待提交对应 CI 镜像、保留回滚材料并部署 cc2api。
- [x] 验证部署状态并推送本任务最终记录。

## 验证记录

- `cargo fmt --check`、`git diff --check` 通过。
- `cargo test -q cch` 的 21 项定向测试通过。
- 改写器定向测试 169 项通过；全量 `cargo test -q` 共 567 项通过（514 单元 + 53 集成），包含 CCH、主模型、Fast Mode/1M 和旧画像回归。
- 260 原始 flow 的 12 类后台路径、763 条请求 UA/beta 全部匹配 fixture；JSONL 中 10 条标题分别为无可选 token 7 条、credit 1 条、server-side + credit 2 条。
- 257 JSONL 可见的 10 类后台路径、474 条请求及 4 条标题全部匹配；stream/archive 的完整证据来自 260 原始 flow。
- 全量格式化尝试因 vendored rustls 缺少 bench/example 文件失败；已撤回本次对 vendor 的格式改动，按项目规定的 `cargo fmt --check` 验证通过。
- spec_update_result：written；仅同步协议规范中的标题白名单、后台路径矩阵及回归断言；规范 diff 与代码/fixture 反查、`git diff --check -- .trellis/spec` 通过。
- 交付追加验证：CI Docker 成功；生产运行精确提交镜像，本地与外部 HTTP 200、DB 完整性 ok、设置/能力/环境/数据卷一致、启动错误计数 0。详情见 release.md。
