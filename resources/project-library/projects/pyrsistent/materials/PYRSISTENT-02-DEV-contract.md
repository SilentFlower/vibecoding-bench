# Engineering contract: PYRSISTENT-02-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair _make_seq_field_type caching so CheckedPVector/CheckedPSet same item_type but different item_invariant identity never reuse an incompatible class; same callable identity reuses safely including unhashable callable objects, without equality/hash assumptions on the policy. New generated-type pickle reductions carry the actual pickleable invariant or an explicit None default marker and reconstruct under that exact policy. Lambdas/closures retain standard pickle limitations and must fail clearly rather than substitute another rule. Legacy three-argument payloads lack enough policy information: reject with a clear trusted-model migration instruction; an explicit fourth policy/default marker supports deliberate restoration. Preserve ordinary default-field pickle roundtrips and class names without silently decoding old ambiguous data under a wrong invariant.

Deliver real implementation, original-failing public tests at library/tests/test_development_pyrsistent_02_dev.py, and English compatibility documentation at library/docs/development-pyrsistent-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/pyrsistent/_field_common.py
- library/tests/test_development_pyrsistent_02_dev.py
- library/docs/development-pyrsistent-02-dev.md
