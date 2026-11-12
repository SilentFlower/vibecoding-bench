# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add optional serializer(record_snapshot, formatted_text) to Logger.add and real Handler emission, independently per sink and before enqueue. Require callable or None and reject simultaneous serialize=True; default boolean JSON output remains unchanged. Pass a deep detached supported record graph (traceback may be retained read-only), preserving other sinks/original nested extra/record attrs against callback mutation; unsupported deepcopy values fail under existing catch policy. Require a string result with callback-owned terminators, invoke exactly once per emitted handler record on the producer thread, and keep catch=False exception propagation and queue completion. Never route custom encoding through a replacement fake sink.

Deliver meaningful original-failing public regression tests at library/tests/test_development_loguru_o04_dev.py and concise English compatibility documentation at library/docs/development-loguru-o04-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/loguru/_logger.py
- library/loguru/_handler.py
- library/tests/test_development_loguru_o04_dev.py
- library/docs/development-loguru-o04-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
