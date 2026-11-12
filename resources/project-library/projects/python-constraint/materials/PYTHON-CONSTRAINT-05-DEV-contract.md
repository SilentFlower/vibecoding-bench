# Engineering contract: PYTHON-CONSTRAINT-05-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add constraint.cardinality.GlobalCardinality(value_bounds,closed=True) as a real Constraint. Snapshot each value min/max nonnegative strict integer bounds; simultaneously enforce per-value counts, using assigned counts and remaining-domain support as safe necessary pruning conditions. closed=True excludes unlisted values; closed=False allows them. Do not confuse one combined SomeInSet count with independent bounds. Reject repeated variables and invalid bound shapes/ranges; impossible but structurally legal bounds produce no solutions. Forward checking must preserve every brute-force legal assignment across solver modes; unary preprocessing must preserve the earlier declared-domain isolation. Document that this is safe support pruning, not a claim of complete generalized arc consistency.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_constraint_05_dev.py, and English compatibility documentation at library/docs/development-python-constraint-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/constraint/cardinality.py
- library/tests/test_development_python_constraint_05_dev.py
- library/docs/development-python-constraint-05-dev.md
