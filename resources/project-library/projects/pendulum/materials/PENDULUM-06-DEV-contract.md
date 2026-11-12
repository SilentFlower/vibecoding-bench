# Engineering contract: PENDULUM-06-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add pendulum.business.BusinessCalendar immutable caller-supplied date holidays and weekday weekend policy, no downloads. Provide is_business_day, signed add_business_days, next_business_day(include_current=False), and signed half-open count. Zero addition preserves identity, nonbusiness starts count following eligible days, negatives reverse, Pendulum Date/DateTime use calendar-day add preserving type/timezone/wall clock. Freeze mutable inputs, reject all-seven weekend/invalid weekdays or datetime holiday objects. Existing ordinary date add remains unchanged; finite local synthetic dates only.

Deliver real implementation, original-failing public tests at library/tests/test_development_pendulum_06_dev.py, and English compatibility documentation at library/docs/development-pendulum-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/pendulum/business.py
- library/tests/test_development_pendulum_06_dev.py
- library/docs/development-pendulum-06-dev.md
