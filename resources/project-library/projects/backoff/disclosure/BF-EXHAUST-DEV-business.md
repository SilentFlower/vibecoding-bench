# Delivery and verification boundaries

Repair on_exception so exhausting a finite wait generator follows raise_on_giveup in both synchronous and asynchronous execution: False returns None; True (including the default) propagates the same last exception object. Preserve the exact number of target attempts, zero/finite waits, exactly one giveup callback with exception and tries, awaited async callbacks, handler-error propagation, ordinary success and on_predicate behavior. Do not add sleeping/network calls to tests, change unrelated retry policies, or intercept exceptions outside the configured exception type.

Deliver source changes and public regressions rather than an investigation report alone. Investigate and propose a plan, obtain confirmation, and implement in the same original conversation. Rework actual reported failures. Check original failures, reference passes, and the complete frozen upstream regression separately; reference results do not count as model results.
