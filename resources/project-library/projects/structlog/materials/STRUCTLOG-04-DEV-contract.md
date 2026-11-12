# Engineering contract: STRUCTLOG-04-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add EventProjector(fields,keep=(),missing="error"/"omit"/"default",default=None). Explicit output-alias to tuple/list path segments, str dict keys and nonnegative int list indexes, no implicit dotted-path interpretation or Python attribute access. Only retain requested top-level fields plus projections; reject alias/keep collision and invalid paths before processing. Actual None is present, missing paths follow explicit policy. Return new outer event preserving payload identity and source; do not infer entire schema or expand object tree.

Deliver real implementation, original-failing public tests at library/tests/test_development_structlog_04_dev.py, and English compatibility documentation at library/docs/development-structlog-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/structlog/processors.py
- library/src/structlog/_event_projector.py
- library/tests/test_development_structlog_04_dev.py
- library/docs/development-structlog-04-dev.md
