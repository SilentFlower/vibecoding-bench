# Engineering contract: TEXTDISTANCE-05-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add textdistance.bounded.bounded_levenshtein(left,right,cutoff,qval=1,test_func=None) returning the exact unit-cost distance when <= cutoff and None otherwise. Implement valid length-difference rejection and a banded dynamic program with sparse rows, not a full matrix followed by cosmetic truncation. Preserve prepared words/qgrams, arbitrary equality predicates, Unicode and exact cutoff equality. Validate strict nonnegative integer cutoff (not bool); no normalized cutoff ambiguity or optional-backend bypass. Demonstrate actual reduced comparisons for long narrow-band inputs and never expose None as a real score.

Deliver real implementation, original-failing public tests at library/tests/test_development_textdistance_05_dev.py, and English compatibility documentation at library/docs/development-textdistance-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/textdistance/bounded.py
- library/tests/test_development_textdistance_05_dev.py
- library/docs/development-textdistance-05-dev.md
