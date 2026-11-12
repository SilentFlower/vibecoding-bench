# Engineering contract: LOGURU-O01-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Logger.handler_snapshot() returning an id-sorted tuple of immutable detached scalar mappings: id, sink_type (actual adapter class), level, formatter static/callable, filter none/callable, enqueue, serialize and stopped. Capture under the existing core lock for consistent concurrent add/remove views. Never expose core/handler/sink/callback objects, call their business methods or repr, or mutate configuration while inspecting it. Old snapshots remain stable after removal. Keep existing repr/add/remove semantics and demonstrate multiple actual sink types and concurrent configuration reads.

Deliver meaningful original-failing public regression tests at library/tests/test_development_loguru_o01_dev.py and concise English compatibility documentation at library/docs/development-loguru-o01-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/loguru/_logger.py
- library/tests/test_development_loguru_o01_dev.py
- library/docs/development-loguru-o01-dev.md
