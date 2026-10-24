# Engineering contract: TRANSITIONS-03-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Isolate caller-owned config before MarkupMachine processing and generate_base_model removes/derives models. Copy built-in dict/list/tuple recursively with shared-alias preservation, retain opaque model/callback identity rather than arbitrary deepcopy, explicitly reject container cycles. Accept read-only outer Mapping by copying dict. Repeated model-code generation and multiple simple/hierarchical machine construction must leave original models/nested states/transitions unchanged. Internal mutable markup behavior remains supported; no promise to freeze arbitrary business objects.

Deliver real implementation, original-failing public tests at library/tests/test_development_transitions_03_dev.py, and English compatibility documentation at library/docs/development-transitions-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/transitions/extensions/markup.py
- library/transitions/experimental/utils.py
- library/transitions/_config.py
- library/tests/test_development_transitions_03_dev.py
- library/docs/development-transitions-03-dev.md
