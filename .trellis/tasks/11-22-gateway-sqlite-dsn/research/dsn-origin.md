# 误建目录的来源

- 2026 年 11 月 19 日 23:08:09（Asia/Shanghai），Codex 会话 `01a1f329-5cea-72f0-8586-c21f5323b8b2` 的本地验证通过 `mktemp -d /tmp/flower2api-agy-migration.XXXXXXXX` 建立临时目录，随后向 Gateway 的 `database-migrations apply` 传入 `DATABASE_DSN=sqlite:…`。会话随后的工具记录确认了随机后缀 `uLnOVoO1`。
- 仓库内 `sqlite:`、`sqlite:/tmp` 与最终的 `sqlite:/tmp/flower2api-agy-migration.uLnOVoO1` 在同一秒创建。这条目录链只有误建的空子目录。
- `config.rs` 将 `DATABASE_DSN` 原样交给启动及维护入口。旧 `init_db` 用原始 DSN 作为 `Path` 建父目录，再给连接串补上 scheme。SQLx 的 SQLite 解析用 `trim_start_matches("sqlite:")` 连续去掉相同前缀。普通 `sqlite:/…` 能连接到实际文件。父目录创建此前已落在仓库内。
- 使用提交 `82601113` 编译结果，在临时工作目录执行同样的前缀与维护入口。命令成功，SQLite 文件位于实际目标，工作目录下同时出现字面量 `sqlite:`。整个复现仅使用临时库。

## 回归与清理

- SQLite 连接池集成测试 3 项通过。验证文件名解码、迁移子命令的只读及符号链接保护，以及 A 的级联行为。
- 数据库迁移单元测试 10 项通过，包括历史台账、幂等和损坏拒绝。
- 三层误建目录经 `find` 核对为空目录链，逐级使用 `rmdir` 移除。仓库工作目录的 `sqlite:` 已消失。
