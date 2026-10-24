# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement statemachine.journal.dumps_journal(results,*,max_records=10000) and loads_journal(document,*,max_records=10000) using completed EventResult/Call/Snapshot types. Schema1 records contain contiguous index, event/args/kwargs, passed/error, before/after configurations and actual result/error; support empty journals and Unicode JSON-compatible values. Validate version, exact record/state structure, counts, order, statuses, duplicate JSON keys, finite values and immediate event control policies. Restore independent data records without importing machine classes, eval or sending events. Unsupported callback result serialization must fail, not stringify objects.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_sm_journal_dev.py and concise English compatibility documentation at library/docs/development-sm-journal-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/statemachine/journal.py
- library/development_tests/test_development_sm_journal_dev.py
- library/docs/development-sm-journal-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
