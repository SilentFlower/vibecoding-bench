# 修复分批占位字符串与真实业务文本冲突

固定源码：https://github.com/pytoolz/toolz @ 451af60dec590a6010e2babdbf391ea8f815122f。

Repair partition and partition_all so any ordinary string, specifically the pinned implementation's '__no__pad__' literal, remains real data and can also be an explicitly supplied padding value. Missing slots must be recognized by an unambiguous internal identity marker, never by comparing business values. Preserve tuple batches, default truncation for partition, partial final groups for partition_all, lazy finite prefixes of infinite input, existing at-most-one-batch lookahead, original invalid-__len__ diagnostics, top-level/curried APIs, and all existing frozen tests.

公开测试见同目录 development-tests.py。请在授权测试路径交付能在原版失败的回归，不修改现有测试控制或依赖；文档路径需说明行为、边界和兼容政策。私有验收独立执行，公开样例不代表全部边界。
