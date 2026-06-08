# cc2api API 模式 max_tokens 对齐 Claude Code 抓包

## Implementation Checklist

- [x] 阅读 cc2api `rewriter.rs` 现有 `rewrite_messages` 和测试风格。
- [x] 在 API 模式分支引入 `normalize_api_max_tokens`，替换现有 `>32768 => 16384` 逻辑。
- [x] 添加/更新单元测试覆盖 PRD acceptance criteria。
- [x] 运行相关 Rust 测试。
- [x] 复查 diff，确认没有动到 Claude Code 模式和无关文件。

## Validation

- `docker run --rm -v /root/project/cc2api:/work -w /work rust:1.86-bookworm sh -c 'export PATH=/usr/local/cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin; cargo test rewriter --lib'`
- 如测试名更具体，运行对应 `cargo test <test_name> --lib`

## Validation Results

- `cargo test rewriter --lib`：32 passed, 0 failed。
- `git diff --check`：通过。
- `rustfmt --edition 2024 --check src/service/rewriter.rs`：仍失败于该文件既有历史格式差异（import 排序、旧 `find_cch_value` 换行），本次新增代码对应的 rustfmt 差异已修复，未应用全文件格式化以避免无关 diff。

## Review Gates

- 实现前确认任务已 `start`。
- 实现后运行 Trellis check。
