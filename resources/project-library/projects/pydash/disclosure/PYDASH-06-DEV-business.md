# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add explicit pydash.async_flow.async_flow and top-level callable export. First function receives original args/kwargs; subsequent functions receive one completed result, awaiting any inspect.isawaitable value including custom awaitables. Run entirely in caller event loop, propagate exceptions and cancellation without later steps, validate callables up front. Empty flow is identity for one positional value or None for zero; reject extra args/kwargs. Existing synchronous flow/flow_right remain unchanged, no internal asyncio.run.

Deliver real implementation, original-failing public tests at library/tests/test_development_pydash_06_dev.py, and English compatibility documentation at library/docs/development-pydash-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/pydash/async_flow.py
- library/src/pydash/__init__.py
- library/tests/test_development_pydash_06_dev.py
- library/docs/development-pydash-06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
