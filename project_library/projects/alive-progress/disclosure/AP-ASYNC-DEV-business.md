# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement alive_progress.asyncio.alive_async_it(source,total=None,*,finalize=None,**bar_options) as a native async iterator using the real alive_bar handle and completed snapshots. Yield original items in order without prefetching, increment only when the consumer resumes past a yielded item, and invoke an explicit sync or awaitable finalizer exactly once only after normal exhaustion, including empty input/falsey callables. Early aclose, cancellation and source errors propagate/clean progress context without success finalization. Reject manual mode and invalid callbacks before reading the source; caller owns the source and rendering remains configured through original bar options.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ap_async_dev.py and concise English compatibility documentation at library/docs/development-ap-async-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/alive_progress/asyncio.py
- library/development_tests/test_development_ap_async_dev.py
- library/docs/development-ap-async-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
