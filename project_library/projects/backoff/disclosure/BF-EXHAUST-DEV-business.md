# 交付验收边界

Repair on_exception so exhausting a finite wait generator follows raise_on_giveup in both synchronous and asynchronous execution: False returns None; True (including the default) propagates the same last exception object. Preserve the exact number of target attempts, zero/finite waits, exactly one giveup callback with exception and tries, awaited async callbacks, handler-error propagation, ordinary success and on_predicate behavior. Do not add sleeping/network calls to tests, change unrelated retry policies, or intercept exceptions outside the configured exception type.

必须完成源码与公开回归交付，不能只报告调查结论。先调查与提出方案，确认后在同一原会话实施，依据真实失败返工。原版失败、参考实现通过和冻结完整上游回归分别核对，不把参考成绩算作模型成绩。
