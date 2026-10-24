# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add constraint.tables.AllowedTuples/ForbiddenTuples as real Constraint subclasses, with copied immutable row values, explicit variable-column order, shape/duplicate-variable checks and bounded max_rows preflight. Allowed tables filter support against assigned values AND remaining domains and prune only unsupported values in forward-check mode; forbidden tables reject exact complete rows and safely prune a single remaining variable. Support nonnumeric and unhashable comparable domain values without requiring hash-based membership. Empty allowed table is unsatisfiable, empty forbidden table imposes no restriction. Preserve original solvers and the earlier per-query independent Domain contract, including unary preprocessing without permanent model-domain mutation.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_constraint_04_dev.py, and English compatibility documentation at library/docs/development-python-constraint-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/constraint/tables.py
- library/tests/test_development_python_constraint_04_dev.py
- library/docs/development-python-constraint-04-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
