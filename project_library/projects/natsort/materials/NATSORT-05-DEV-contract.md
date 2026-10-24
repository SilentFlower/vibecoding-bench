# Engineering contract: NATSORT-05-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add natsort.search.NaturalSortedIndex(iterable,*,key=None,alg=ns.DEFAULT,reverse=False). Snapshot original record order and precomputed natural keys, reject unordered input without sorting, support rank(value,side), count(value), and between(start,stop,include_start,include_stop) with None for unbounded ranges. Query values are already extracted fields; results preserve original records and input direction. Equal natural keys and reverse indexes need correct binary boundaries. Locale changes invalidate locale indexes; caller rebuilds after record/key-policy mutation. Do not change ordinary natsort.

Deliver real implementation, original-failing public tests at library/tests/test_development_natsort_05_dev.py, and English compatibility documentation at library/docs/development-natsort-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/natsort/search.py
- library/tests/test_development_natsort_05_dev.py
- library/docs/development-natsort-05-dev.md
