# Engineering contract: SG-BOUNDS-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement sqlglot.report_bounds.bounded_query(query,max_rows,*,offset=0,dialect=None) using completed single-query copying and real AST builders. Wrap original query as an aliased subquery and apply outer limit/offset; never overwrite existing inner LIMIT/OFFSET/order/CTEs or apply limit independently to each UNION branch. Accept zero limit, reject negative/noninteger/bool values, preserve original AST and compile through requested output dialect. This bounds final row count, does not execute SQL or guarantee implicit order across dialects.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_sg_bounds_dev.py and concise English compatibility documentation at library/docs/development-sg-bounds-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/sqlglot/report_bounds.py
- library/development_tests/test_development_sg_bounds_dev.py
- library/docs/development-sg-bounds-dev.md
