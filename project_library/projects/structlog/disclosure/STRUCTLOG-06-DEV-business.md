# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add ZonedTimeStamper(zone,*,timespec="microseconds",key="timestamp",clock=None) processor in structlog.processors. Accept tzinfo or standard ZoneInfo name, convert an actual aware datetime instant with astimezone, output ISO offset with selected supported precision, mutate/return same event. Default clock UTC now, injectable aware clock for deterministic proof, reject naive/wrong clock and unsupported precision. Existing TimeStamper utc/local/UNIX outputs/pickle stay unchanged. No timezone guessing, changing OS TZ or online data.

Deliver real implementation, original-failing public tests at library/tests/test_development_structlog_06_dev.py, and English compatibility documentation at library/docs/development-structlog-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/structlog/processors.py
- library/src/structlog/_zoned_timestamp.py
- library/tests/test_development_structlog_06_dev.py
- library/docs/development-structlog-06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
