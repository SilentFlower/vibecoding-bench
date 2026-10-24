# Engineering contract: PYRSISTENT-06-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add pyrsistent.merge.deep_merge(left,right,conflict="replace",max_depth=32) and MergeConflict.path. left is a PMap and right accepts mapping or pairs through the earlier delivered update capability. Merge mapping/mapping branches recursively, leaf conflicts replace by default, raise with full tuple path or call an explicit (path,old,new) resolver. Equal/unmodified values share existing branches; new builtin containers are frozen with strict=False to preserve already-persistent checked types. Use actual evolvers, preserve CheckedPMap validation, reject unsupported policy/depth and surface type/source/callback failures without changing left. Do not claim automatic concatenation of sequences, arbitrary object deepcopy or a concurrent transaction. Cyclic/unrepresentable new builtin containers fail explicitly.

Deliver real implementation, original-failing public tests at library/tests/test_development_pyrsistent_06_dev.py, and English compatibility documentation at library/docs/development-pyrsistent-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/pyrsistent/merge.py
- library/tests/test_development_pyrsistent_06_dev.py
- library/docs/development-pyrsistent-06-dev.md
