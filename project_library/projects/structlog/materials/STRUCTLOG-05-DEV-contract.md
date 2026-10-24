# Engineering contract: STRUCTLOG-05-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Extend CapturingLogger/Factory optional capacity=None with overflow drop_oldest/reject_new. Preserve default unlimited calls list and repr, all dynamic methods and one cached logger per factory. Nonnegative strict integer capacity, zero records nothing, total counts every call and dropped counts each unretained/evicted call. Snapshot returns tuple with copied kwargs containers but shared nested business objects. No concurrent producer guarantees or silently changing stats when caller manually edits calls.

Deliver real implementation, original-failing public tests at library/tests/test_development_structlog_05_dev.py, and English compatibility documentation at library/docs/development-structlog-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/structlog/testing.py
- library/tests/test_development_structlog_05_dev.py
- library/docs/development-structlog-05-dev.md
