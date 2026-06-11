# cc2api 2.1.173 抓包差异分析实施计划

## Implementation Checklist

- [x] 从远程 `data/flows` 查找 `bca74ce4196b`、`6e65bb7cb888`、`7445da8ab9af` 的完整路径。
- [x] 拉取三条 run 目录到本地，并校验 `capture_index.json`、`http_capture.jsonl`、`stats.jsonl`、`.flow` 是否存在。
- [x] 读取旧样本 `3075/3078/3085/3088` 和新样本的安全索引，建立样本矩阵。
- [x] 编写或复用临时安全分析脚本，输出 header/beta/body/telemetry/bootstrap 摘要。
- [x] 复算 `cc_version` 后缀命中情况。
- [x] 按旧完整 body、`2.1.172` Opus 规则、`2.1.172` Fable 规则复算 CCH 命中情况。
- [x] 产出 `research/cc2api-2-1-173-capture-diff.md`，只记录安全摘要和升级建议。
- [x] 对照 `cc2api` 当前 `version_profile`、`rewriter`、`telemetry`、`settings_store` 给出修改建议，不直接改代码。
- [x] 将 `/root/project/cc2api` 默认 Claude Code 画像升级到 `2.1.173`。
- [x] 将默认允许版本范围扩到 `2.1.89-2.1.173`。
- [x] 将 `2.1.173` 纳入 `2.1.172` 同款 CCH seed 和输入规范化规则。
- [x] 更新相关 Rust 测试、Web 设置默认值和 README。
- [x] 保持 `allow_1m_models` 只做 1M beta 透传白名单，不新增 Fable 自动注入。

## Validation

- `find data/flows -path '*<run_id>*' -maxdepth ...` 确认三条新 run 已落盘。
- 对每个 run 校验关键文件存在且非空。
- `git status --short` 确认没有把完整抓包原文加入 git 跟踪。
- [x] `/root/project/cc2api` 内运行 `cargo fmt --check`。
- [x] `/root/project/cc2api` 内运行版本、CCH、Fable、telemetry、access policy 相关定向测试。
- [x] 如时间允许，运行 `/root/project/cc2api` 全量 `cargo test`。

## Review Gates

- 分析报告写入前先确认输出中不含 Authorization、Cookie、OAuth token、账号邮箱、完整 prompt 或完整响应正文。
- 若 CCH 或 `cc_version` 不命中，不直接推断为算法变化，先记录样本类型、模型和 body profile 差异。
