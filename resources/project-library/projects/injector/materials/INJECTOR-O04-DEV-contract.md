# Engineering contract: INJECTOR-O04-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add ContextScope(Scope), contextscope decorator and enter() context using an instance-owned ContextVar plus thread/task ownership. Actual Injector.get of a bound class reuses one successful instance within its explicit active scope, nested enter gets fresh instances then restores outer tokens, and exit/failure/cancellation removes scope state. Concurrent asyncio tasks each explicitly enter and remain isolated; inherited parent context in a child task is not implicitly owned and must reject get until entering. Failed providers never populate cache. Preserve NoScope/Singleton/ThreadLocal semantics and do not implicitly close unmanaged resources or use a global mutable task cache.

Deliver meaningful original-failing public regression tests at library/tests/test_development_injector_o04_dev.py and concise English compatibility documentation at library/docs/development-injector-o04-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/injector/__init__.py
- library/tests/test_development_injector_o04_dev.py
- library/docs/development-injector-o04-dev.md
