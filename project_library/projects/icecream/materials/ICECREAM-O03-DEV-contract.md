# Engineering contract: ICECREAM-O03-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Extend Timer.__call__ for inspect.iscoroutinefunction only, using the accepted context/ownership timing stack. Start on actual await execution, await the original coroutine and output only after completion/failure/cancellation, preserving value, metadata and original exception. Same timer recursive/interleaved tasks must remain isolated; disabled output still awaits/cleans exactly once. Keep existing synchronous decorator behavior and explicitly exclude async generators or ordinary functions returning an Awaitable rather than silently changing their semantics.

Deliver meaningful original-failing public regression tests at library/tests/test_development_icecream_o03_dev.py and concise English compatibility documentation at library/docs/development-icecream-o03-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/icecream/icecream.py
- library/tests/test_development_icecream_o03_dev.py
- library/docs/development-icecream-o03-dev.md
