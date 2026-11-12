# Engineering contract: BF-AWAIT-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Repair asynchronous giveup and event callback adaptation to await any actual Awaitable result, including async __call__ instances and ordinary wrappers returning coroutine objects. Synchronous callbacks remain supported and are invoked exactly once; await results before deciding giveup and before completing the event. Preserve callback exception identity and prevent never-awaited warnings. Do not expand predicate or target APIs, change synchronous retry policy or swallow callback exceptions.

Deliver meaningful original-failing public regression tests at library/tests/test_development_bf_await_dev.py and concise English compatibility documentation at library/docs/development-bf-await-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/backoff/_async.py
- library/tests/test_development_bf_await_dev.py
- library/docs/development-bf-await-dev.md
