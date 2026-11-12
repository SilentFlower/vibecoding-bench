# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add keyword-only loads=None to JSONLIterator, selecting json.loads by default or a validated explicit callable. Call it once per nonblank candidate line, preserve exact returned object, reverse/rel_seek behavior and existing ignore_errors handling for decoder exceptions. Do not mutate global json.loads, preload the file, or close caller-owned streams. Validate decoder before reading or seeking; support Decimal parse_float and object_pairs_hook through caller-provided decoder functions.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_bo_jsonl_decoder_dev.py and concise English compatibility documentation at library/docs/development-bo-jsonl-decoder-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/boltons/jsonutils.py
- library/development_tests/test_development_bo_jsonl_decoder_dev.py
- library/docs/development-bo-jsonl-decoder-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
