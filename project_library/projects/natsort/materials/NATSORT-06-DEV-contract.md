# Engineering contract: NATSORT-06-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add immutable natsort.records.FieldSortSpec(key,alg=ns.DEFAULT,reverse=False,missing="last") and multisorted(iterable,fields). Fields are ordered highest priority first; each uses its own existing natsort algorithm and direction. Keep stable ties and full original records, consume a one-shot input once and never mutate caller lists. Treat None as missing with explicit first/last/error positions independent of reverse; reject invalid/empty specs and propagate getter errors. Default nested-key and natsorted behavior remain unchanged.

Deliver real implementation, original-failing public tests at library/tests/test_development_natsort_06_dev.py, and English compatibility documentation at library/docs/development-natsort-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/natsort/records.py
- library/tests/test_development_natsort_06_dev.py
- library/docs/development-natsort-06-dev.md
