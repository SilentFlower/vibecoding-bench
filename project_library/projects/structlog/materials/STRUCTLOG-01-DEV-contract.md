# Engineering contract: STRUCTLOG-01-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair shared _items_sorter missing detection with a private sentinel, preserving explicit None for KeyValueRenderer and LogfmtRenderer when drop_missing=True. Cover both ordered+sort paths, false/zero/empty values and duplicate key_order behavior. Keep default absent-field None rendering, ordering, extras sorting and original event-dictionary consumption semantics; do not turn None into an absent field or change serializer rules.

Deliver real implementation, original-failing public tests at library/tests/test_development_structlog_01_dev.py, and English compatibility documentation at library/docs/development-structlog-01-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/structlog/processors.py
- library/tests/test_development_structlog_01_dev.py
- library/docs/development-structlog-01-dev.md
