# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add keyword-only on_error=None to map_except/filter_except, reporting zero-based input index, original item and actual caught exception once per listed conversion failure. Successful map values/filter item identities and lazy prefix consumption remain unchanged. Support falsey callable, validate non-None callbacks, propagate callback exceptions and unlisted exceptions. Restrict map exception catching to function execution, not consumer-injected errors across yield. No internal unbounded error collection.

Deliver real implementation, original-failing public tests at library/tests/test_development_more_itertools_01_dev.py, and English compatibility documentation at library/docs/development-more-itertools-01-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/more_itertools/more.py
- library/tests/test_development_more_itertools_01_dev.py
- library/docs/development-more-itertools-01-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
