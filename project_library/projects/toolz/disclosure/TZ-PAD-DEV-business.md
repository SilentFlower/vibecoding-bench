# 交付验收边界

Repair partition and partition_all so any ordinary string, specifically the pinned implementation's '__no__pad__' literal, remains real data and can also be an explicitly supplied padding value. Missing slots must be recognized by an unambiguous internal identity marker, never by comparing business values. Preserve tuple batches, default truncation for partition, partial final groups for partition_all, lazy finite prefixes of infinite input, existing at-most-one-batch lookahead, original invalid-__len__ diagnostics, top-level/curried APIs, and all existing frozen tests.

必须完成源码与公开回归交付，不能只报告调查结论。先调查与提出方案，确认后在同一原会话实施，依据真实失败返工。原版失败、参考实现通过和冻结完整上游回归分别核对，不把参考成绩算作模型成绩。
