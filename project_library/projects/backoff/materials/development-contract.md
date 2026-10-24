# Apply a consistent give-up policy when a finite retry schedule is exhausted

Pinned source: https://github.com/litl/backoff @ d82b23c42d7a7e2402903e71e7a7f03014a00076.

Repair on_exception so exhausting a finite wait generator follows raise_on_giveup in both synchronous and asynchronous execution: False returns None; True (including the default) propagates the same last exception object. Preserve the exact number of target attempts, zero/finite waits, exactly one giveup callback with exception and tries, awaited async callbacks, handler-error propagation, ordinary success and on_predicate behavior. Do not add sleeping/network calls to tests, change unrelated retry policies, or intercept exceptions outside the configured exception type.

See development-tests.py in this directory for public examples. Deliver original-failing regression tests at the authorized test path without changing existing test controls or dependencies. Document behavior, boundaries, and compatibility policy at the authorized documentation path. Private verification runs independently; public examples do not cover every boundary.
