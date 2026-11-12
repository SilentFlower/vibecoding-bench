# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add constraint.optimization.optimize(problem,objective,direction="min",max_solutions=None) and immutable OptimizationResult(solution,score,examined,complete,reason). Enumerate actual feasible solutions through the selected solver iterator, preserve input-order first tie, snapshot assignments before objective/history and validate finite non-bool numeric scores. Full exhaustion proves optimal/unsatisfiable; reaching a strict nonnegative evaluation budget reports incomplete budget even when total may equal that boundary, without lookahead or false optimality. max_solutions=0 does not start iteration. Always close supported iterators on return/error; unsupported solver iteration remains an explicit capability error, never secretly materialize all solutions. Reuse earlier repeat-string and independent declared-domain behavior so running different objectives never mutates the model.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_constraint_06_dev.py, and English compatibility documentation at library/docs/development-python-constraint-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/constraint/optimization.py
- library/tests/test_development_python_constraint_06_dev.py
- library/docs/development-python-constraint-06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
