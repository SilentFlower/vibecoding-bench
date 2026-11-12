# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add public sort_dict_by_keys and sort_dict_by_values in pydash.objects and top-level exports. Accept Mapping, return a new insertion-ordered dict, support optional key and reverse, stable ties, exact key/value pairing and original value identity. Source order/content never mutate; falsey callable keys still execute, invalid input/key and comparison errors propagate clearly. Existing sort_by/objects API unchanged; do not promise chain methods without implementing their static interface.

Deliver real implementation, original-failing public tests at library/tests/test_development_pydash_03_dev.py, and English compatibility documentation at library/docs/development-pydash-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/pydash/objects.py
- library/src/pydash/__init__.py
- library/tests/test_development_pydash_03_dev.py
- library/docs/development-pydash-03-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
