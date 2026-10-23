# 交付验收边界

Make RepositoryEnv and RepositoryIni accept an optional UTF-8 BOM only at the start of a UTF-8 encoded file, including standard UTF-8 codec aliases and utf-8-sig. Handle empty/BOM-only files and a BOM before a comment. Preserve every later U+FEFF in keys or values, existing Config precedence/casts/defaults, explicitly requested non-UTF8 encodings, and decoding errors. Apply the policy at the actual repository file-reading boundaries, not by global string replacement or modifying os.environ.

必须完成源码与公开回归交付，不能只报告调查结论。先调查与提出方案，确认后在同一原会话实施，依据真实失败返工。原版失败、参考实现通过和冻结完整上游回归分别核对，不把参考成绩算作模型成绩。
