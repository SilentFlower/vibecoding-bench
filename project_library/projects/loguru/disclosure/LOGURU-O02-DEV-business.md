# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Logger.sink_context(sink, **add_options) yielding the actual new handler id and removing only that handler on every exit, including BaseException, using existing queue/file/coroutine remove/stop ownership semantics. Nested contexts and external early removal are supported; caller streams remain open as add/remove already promise. Normal cleanup failure propagates. If body and cleanup both fail, preserve the original body exception and emit a RuntimeWarning for cleanup; do not silence body failures or delete unrelated handlers. Existing queued records finish through normal remove before exit.

Deliver meaningful original-failing public regression tests at library/tests/test_development_loguru_o02_dev.py and concise English compatibility documentation at library/docs/development-loguru-o02-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/loguru/_logger.py
- library/tests/test_development_loguru_o02_dev.py
- library/docs/development-loguru-o02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
