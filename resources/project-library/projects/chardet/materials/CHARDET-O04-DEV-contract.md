# Engineering contract: CHARDET-O04-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement chardet.batch.detect_many(records, *, on_error="continue", should_rename_legacy=False). Lazily process (id, bytes/bytearray) pairs with fresh real detect calls, preserve index/order/duplicate identifiers and local error facts, and provide continue/stop/raise policies. A failed record has no successful result, stop/close must not consume the tail, upstream generator errors propagate and raw bytes must not be misinterpreted as an iterable batch. Preserve standard detection/fallback facts.

Deliver meaningful original-failing public regression tests at library/tests/test_development_chardet_o04_dev.py and concise English compatibility documentation at library/docs/development-chardet-o04-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/chardet/batch.py
- library/tests/test_development_chardet_o04_dev.py
- library/docs/development-chardet-o04-dev.md
