# Engineering contract: FUNCY-O02-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add funcy.async_calc.amemoize/acache using real Funcy SkipMemory and positional-vs-keyword key policy. Cache completed successful values, never coroutine objects, isolate values/pending tasks per event loop, singleflight same-key concurrent calls and shield shared producer from one waiter cancellation. Failures/producer cancellation/SkipMemory never cache; canceled waiters may leave a producer running by documented policy. TTL uses injectable monotonic clock from completion, invalidation supports key_func and generation checks so a detached stale producer cannot overwrite newer cache. Provide invalidate/invalidate_all/cache_info, bounded expired cleanup on access and strict options without changing synchronous memoize/cache.

Deliver meaningful original-failing public regression tests at library/tests/test_development_funcy_o02_dev.py and concise English compatibility documentation at library/docs/development-funcy-o02-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/funcy/async_calc.py
- library/tests/test_development_funcy_o02_dev.py
- library/docs/development-funcy-o02-dev.md
