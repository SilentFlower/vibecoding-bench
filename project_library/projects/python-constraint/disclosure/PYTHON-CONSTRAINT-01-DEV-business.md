# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair Problem._getArgs so parsed string constraints live only in the current solve list, never get appended to the permanent explicit _constraints on every query. Preserve explicitly repeated constraints/callable objects, all existing string-expression semantics and each solver picklable policy; compile failures must not partially alter the model. reset clears string rules as well as regular constraints and variables. Repeated mixed string/function solving, solver changes and later variable declarations retain identical legal solution sets without model-list growth. Deliver a complete state-lifecycle repair, not a cache counter test.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_constraint_01_dev.py, and English compatibility documentation at library/docs/development-python-constraint-01-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/constraint/problem.py
- library/tests/test_development_python_constraint_01_dev.py
- library/docs/development-python-constraint-01-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
