# Engineering contract: PYDASH-04-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add pydash.json_pointer pointer_tokens/get_pointer/set_pointer plus top-level exports. RFC6901 empty root, empty keys, ~0/~1 single-pass decoding and dict/list-only traversal. get returns original identity; set replaces existing list indices, adds dict keys, permits final - append, returns root (empty path returns replacement). Existing parents required; invalid escapes, negative/leading-zero/out-of-range indices and scalar/attribute traversal fail before mutation. Do not reinterpret legacy get/set_ path strings.

Deliver real implementation, original-failing public tests at library/tests/test_development_pydash_04_dev.py, and English compatibility documentation at library/docs/development-pydash-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/pydash/json_pointer.py
- library/src/pydash/__init__.py
- library/tests/test_development_pydash_04_dev.py
- library/docs/development-pydash-04-dev.md
