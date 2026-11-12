# Engineering contract: FUNCY-O03-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add funcy.scoped.wrap_with_factory(factory) without changing wrap_with(ctx). Create fresh no-arg managers per execution; normal sync calls use sync context, generators enter on first consumption and retain resource through yield/throw/close, coroutine and async-generator wrappers accept sync or async managers. Async generator aclose must close the wrapped generator before leaving the manager. Preserve original enter/exit failures, manager suppression policy, function metadata, original exception and cancellation cleanup. Prove repeated calls never reuse one-shot managers and resources remain open only during actual execution.

Deliver meaningful original-failing public regression tests at library/tests/test_development_funcy_o03_dev.py and concise English compatibility documentation at library/docs/development-funcy-o03-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/funcy/scoped.py
- library/tests/test_development_funcy_o03_dev.py
- library/docs/development-funcy-o03-dev.md
