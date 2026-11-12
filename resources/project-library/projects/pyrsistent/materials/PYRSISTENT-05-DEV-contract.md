# Engineering contract: PYRSISTENT-05-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Extend real PMap.update/update_with input adaptation from mapping-only .items() to mappings OR single-pass (key,value) iterables. Preserve multi-source left-to-right order, duplicate-pair last-write or update_fn fold semantics, persistent original ownership and CheckedPMap evolver checks. Consume generators once, propagate malformed pair/source/callback/type failures and never return a partially updated original. Keep pmap constructor and existing union API unchanged because they already support their documented roles; this goal specifically implements missing update input capability.

Deliver real implementation, original-failing public tests at library/tests/test_development_pyrsistent_05_dev.py, and English compatibility documentation at library/docs/development-pyrsistent-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/pyrsistent/_pmap.py
- library/tests/test_development_pyrsistent_05_dev.py
- library/docs/development-pyrsistent-05-dev.md
