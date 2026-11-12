# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair LCSSeq two-input dynamic programming and reconstruction to honor the existing test_func contract, matching the multi-input path. Return matching units from the first input with their original spelling, preserve default == results and stable existing tie behavior, and do not replace arbitrary pairwise predicates with a lowercase/hash-key equivalence assumption. Custom predicates may be nontransitive; errors propagate. No optional backend may bypass the predicate. Deliver a complete repair with public original-failing checks and unchanged upstream tests.

Deliver real implementation, original-failing public tests at library/tests/test_development_textdistance_01_dev.py, and English compatibility documentation at library/docs/development-textdistance-01-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/textdistance/algorithms/sequence_based.py
- library/tests/test_development_textdistance_01_dev.py
- library/docs/development-textdistance-01-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
