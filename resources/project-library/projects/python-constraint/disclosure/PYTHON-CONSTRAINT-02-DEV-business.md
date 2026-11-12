# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair Problem.getSolutionsOrderedList: order=None keeps the prior default value order, every explicit variable sequence (including length one and empty) projects exactly those columns and always returns tuples. Reject string/bytes order, duplicate variables and unknown IDs before search. Preserve arbitrary hashable variable identities without sorting/comparing them. getSolutionsAsListDict must operate on the projected rows and retain its existing validate=True duplicate-projection check; do not silently deduplicate full solutions. Deliver source repair, meaningful public failure cases and compatibility documentation.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_constraint_02_dev.py, and English compatibility documentation at library/docs/development-python-constraint-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/constraint/problem.py
- library/tests/test_development_python_constraint_02_dev.py
- library/docs/development-python-constraint-02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
