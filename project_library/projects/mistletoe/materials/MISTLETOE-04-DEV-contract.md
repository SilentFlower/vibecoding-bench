# Engineering contract: MISTLETOE-04-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair TocRenderer filter_conds ownership. None/default creates a fresh list per renderer; explicit iterables, including generators, are materialized once in order without mutating caller lists. Later caller changes and one renderer edits cannot affect other instances. Preserve filter short-circuit order and propagate callback exceptions.

Deliver real implementation, original-failing public tests at library/tests/test_development_mistletoe_04_dev.py, and English compatibility documentation at library/docs/development-mistletoe-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/mistletoe/contrib/toc_renderer.py
- library/tests/test_development_mistletoe_04_dev.py
- library/docs/development-mistletoe-04-dev.md
