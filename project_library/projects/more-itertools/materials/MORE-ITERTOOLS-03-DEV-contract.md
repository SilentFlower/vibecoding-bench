# Engineering contract: MORE-ITERTOOLS-03-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add windowed_time(iterable,key,span) yielding a tuple of original events for each consumed event, inclusive interval [event_time-span,event_time]. Nondecreasing timestamp requirement, positive numeric/timedelta span, duplicates remain separate input-ordered events. Evict expired items before output, retain no full history, support sparse/empty/cross-day streams and propagate invalid order/arithmetic. Event time only, no clock or fake constant-memory claim when many events share span.

Deliver real implementation, original-failing public tests at library/tests/test_development_more_itertools_03_dev.py, and English compatibility documentation at library/docs/development-more-itertools-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/more_itertools/more.py
- library/more_itertools/_windowed_time.py
- library/tests/test_development_more_itertools_03_dev.py
- library/docs/development-more-itertools-03-dev.md
