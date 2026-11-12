# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Table.query_page(cond=None, *, limit=100, after=None) returning (documents,next_cursor). Integer document IDs are sorted ascending, after is exclusive, condition is optional and evaluated on detached Documents. Return at most limit rows; next_cursor is the last returned matching ID only if another match exists, otherwise None. Support sparse IDs, insert/remove between pages, MemoryStorage and JSONStorage. Deep-copy returned data so caller or predicate changes cannot mutate storage. Validate limit 1..1000 and nonnegative integer cursor, excluding booleans. This is keyset pagination, without snapshot/concurrent-writer guarantees.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_td_page_dev.py and concise English compatibility documentation at library/docs/development-td-page-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/tinydb/table.py
- library/development_tests/test_development_td_page_dev.py
- library/docs/development-td-page-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
