# 统一有限重试耗尽时的放弃政策

固定源码：https://github.com/litl/backoff @ d82b23c42d7a7e2402903e71e7a7f03014a00076。

Repair on_exception so exhausting a finite wait generator follows raise_on_giveup in both synchronous and asynchronous execution: False returns None; True (including the default) propagates the same last exception object. Preserve the exact number of target attempts, zero/finite waits, exactly one giveup callback with exception and tries, awaited async callbacks, handler-error propagation, ordinary success and on_predicate behavior. Do not add sleeping/network calls to tests, change unrelated retry policies, or intercept exceptions outside the configured exception type.

公开测试见同目录 development-tests.py。请在授权测试路径交付能在原版失败的回归，不修改现有测试控制或依赖；文档路径需说明行为、边界和兼容政策。私有验收独立执行，公开样例不代表全部边界。
