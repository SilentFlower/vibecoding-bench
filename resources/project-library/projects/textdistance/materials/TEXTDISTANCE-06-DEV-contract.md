# Engineering contract: TEXTDISTANCE-06-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add textdistance.retrieval Match and extract(query, choices, scorer, k=5, direction="distance", threshold=None, max_candidates=None). Stream (id,value) records through the actual scorer; maintain O(k) scored result storage with explicit lower-is-better distance or higher-is-better similarity, inclusive threshold and input-order stable ties. Return original id/value/score/index without comparing IDs or merging duplicates. k=0 must not consume choices. Bad score/nonfinite/bool values or insufficient candidate budget raise rather than return an apparently complete partial ranking. Keep scoring primitives unchanged and support ordinary callables and real built-in algorithms.

Deliver real implementation, original-failing public tests at library/tests/test_development_textdistance_06_dev.py, and English compatibility documentation at library/docs/development-textdistance-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/textdistance/retrieval.py
- library/tests/test_development_textdistance_06_dev.py
- library/docs/development-textdistance-06-dev.md
