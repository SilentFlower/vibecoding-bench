# Engineering contract: PYTHON-CONSTRAINT-03-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair actual domain ingestion: addVariable checks/materializes the domain, not the variable identity, so tuple/hashable IDs and one-shot iterables work. addVariables materializes a shared iterable once, preflights duplicate/existing IDs, prepares all independent domains before commit and leaves no partial variables on empty/domain-source/copy failure. Preserve Domain subclass deepcopy semantics and never share hidden-value state. Allocate fresh Domain copies for each _getArgs solve so preprocessing does not permanently shrink declared model domains. Preserve original list/set/range and ordinary solver results; arbitrary user constraint external side effects are outside this isolation guarantee.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_constraint_03_dev.py, and English compatibility documentation at library/docs/development-python-constraint-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/constraint/problem.py
- library/tests/test_development_python_constraint_03_dev.py
- library/docs/development-python-constraint-03-dev.md
