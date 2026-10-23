# 业务验收边界

Extend the actual portion.iterate API with keyword-only checked=False and max_items=None. With checked=True, each evaluated numeric or callable step must strictly advance in the requested direction; reject a zero/stagnating/wrong-direction step with ValueError, including while skipping an open starting boundary. max_items is a nonnegative integer excluding bool, limits total yielded values across disjoint atomic parts, and 0 must return without invoking base or step. Stop at the limit without an extra step call. Keep default legacy behavior, lazy finite prefixes of unbounded intervals, custom date steps and bases, reverse ordering, existing callback exceptions, all original tests and specialized create_api exports. Do not use wall clocks, background threads or eager enumeration to simulate a limit.

调查后提出兼容方案，确认后在同一会话完成实现、文档和公开回归。重复请求、异常分支与回归不另算新项目；不能只报告已有库的零步行为。
