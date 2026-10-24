# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add sessionize(iterable,key,gap) yielding ordered lists of original events. Start a new session only when consecutive event gap is STRICTLY greater than nonnegative numeric/timedelta gap, preserving identity and source order; equality stays in session. Support one-shot/empty/duplicate/cross-day inputs, reject observed reverse timestamps and negative gap, propagate incompatible key/arithmetic errors. Use no real clock and keep only current session plus lookahead, with documented full-session memory.

Deliver real implementation, original-failing public tests at library/tests/test_development_more_itertools_02_dev.py, and English compatibility documentation at library/docs/development-more-itertools-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/more_itertools/more.py
- library/more_itertools/_sessionize.py
- library/tests/test_development_more_itertools_02_dev.py
- library/docs/development-more-itertools-02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
