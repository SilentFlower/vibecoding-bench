# Engineering contract: RICH-05-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair Traceback SyntaxError-derived capture to normalize msg, filename and source text through the existing safe_str helper, preserving actual original object fields and stable <exception str() failed> fallback. Actual Console rendering must survive numeric/container/custom messages instead of raising a second TypeError that hides the original problem. Preserve ordinary string diagnostics and offset/line positioning. Apply across the earlier accepted cyclic/shared exception graph without losing its identity bound; this delivery depends on that graph repair and does not re-count exception traversal as a separate phase.

Deliver real implementation, original-failing public tests at library/tests/test_development_rich_05_dev.py, and English compatibility documentation at library/docs/development-rich-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/rich/traceback.py
- library/tests/test_development_rich_05_dev.py
- library/docs/development-rich-05-dev.md
