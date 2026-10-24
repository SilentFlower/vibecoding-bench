# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Extend UnicodeDecoder with opt-in recursive=False/max_depth=32. Recursive mode builds new built-in dict/list/tuple containers, decodes bytes values using configured encoding/errors, leaves keys and opaque objects untouched. Preserve container types, reject active-path cycles with path diagnostics (shared DAG is legal), enforce finite depth. Default shallow in-place behavior stays unchanged. No arbitrary object getter/deepcopy or claim to preserve alias identity of copied shared subtrees.

Deliver real implementation, original-failing public tests at library/tests/test_development_structlog_02_dev.py, and English compatibility documentation at library/docs/development-structlog-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/structlog/processors.py
- library/tests/test_development_structlog_02_dev.py
- library/docs/development-structlog-02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
