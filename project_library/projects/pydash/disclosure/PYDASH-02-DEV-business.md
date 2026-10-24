# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Use None exclusively for an omitted retry on_exception callback. Validate every non-None value as callable, determine its accepted arguments even when falsey, and invoke after each retryable exception including the final attempt. Support callable objects with false __bool__ or __len__, zero-arg callbacks and final original exceptions. Do not retry callback exceptions, change sleeps/counts, or catch non-retryable exceptions.

Deliver real implementation, original-failing public tests at library/tests/test_development_pydash_02_dev.py, and English compatibility documentation at library/docs/development-pydash-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/pydash/utilities.py
- library/tests/test_development_pydash_02_dev.py
- library/docs/development-pydash-02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
