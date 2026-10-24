# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add textdistance.weighted.WeightedLevenshtein with finite nonnegative insertion/deletion/substitution constants or token callbacks, qval and test_func using actual pinned preparation. Compute exact minimum path costs from source to target; insertion/deletion may be asymmetric, substitution may be more expensive than delete+insert, zero costs and fractional costs are legitimate. Validate bad constants at configuration and bad callback results when used; bool/negative/NaN/Inf reject. Equal units cost zero according to the predicate. Expose call/distance without claiming every asymmetric policy is a mathematical metric or inventing a normalized bound. Original Levenshtein and optional backend behavior stay unchanged.

Deliver real implementation, original-failing public tests at library/tests/test_development_textdistance_04_dev.py, and English compatibility documentation at library/docs/development-textdistance-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/textdistance/weighted.py
- library/tests/test_development_textdistance_04_dev.py
- library/docs/development-textdistance-04-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
