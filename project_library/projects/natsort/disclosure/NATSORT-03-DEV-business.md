# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add natsort.topk.natural_topk(iterable,count,*,key=None,alg=ns.DEFAULT,reverse=False,indices=False). Results equal the corresponding stable natsorted prefix, including equal-key stability in reverse order and original-index output. Consume a one-shot stream once with O(K) selection storage, not a full input list; count=0 must not touch input. Reject negative/noninteger count, support counts larger than input, preserve key exceptions and original algorithms. Do not claim fewer input reads or change natsorted.

Deliver real implementation, original-failing public tests at library/tests/test_development_natsort_03_dev.py, and English compatibility documentation at library/docs/development-natsort-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/natsort/topk.py
- library/tests/test_development_natsort_03_dev.py
- library/docs/development-natsort-03-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
