# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add sized_iterator(...,strict=False) with opt-in exact observed-length validation. Strict nonnegative integer declaration, preserve fixed __len__ as declared length and lazy consumption. At premature exhaustion raise ValueError, or consume first extra item then raise before yielding it; previously valid prefix may already be delivered. After mismatch become exhausted, do not repeatedly consume. Exact/zero lengths pass; default remains unchecked historical behavior. Early consumer stop cannot claim full-length validation.

Deliver real implementation, original-failing public tests at library/tests/test_development_more_itertools_06_dev.py, and English compatibility documentation at library/docs/development-more-itertools-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/more_itertools/more.py
- library/tests/test_development_more_itertools_06_dev.py
- library/docs/development-more-itertools-06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
