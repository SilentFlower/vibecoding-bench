# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair textdistance.utils.words_combinations(f,*texts) for actual built-in distances and arbitrary numeric callables without assuming a nonexistent equality attribute. Add explicit direction distance/similarity, max_permutations positive call budget and truncate=False policy. Preserve full word counts by default; opt-in truncation is explicit. Generate unique permutations for duplicate words and preflight the whole Cartesian-product budget before any scoring; reject insufficient budgets rather than return a partial optimum. Empty documents have one empty permutation, no documents reject, bad direction/nonfinite/bool scores reject. Evaluate multi-document callables correctly, propagate their real errors and document factorial limits.

Deliver real implementation, original-failing public tests at library/tests/test_development_textdistance_03_dev.py, and English compatibility documentation at library/docs/development-textdistance-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/textdistance/utils.py
- library/tests/test_development_textdistance_03_dev.py
- library/docs/development-textdistance-03-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
