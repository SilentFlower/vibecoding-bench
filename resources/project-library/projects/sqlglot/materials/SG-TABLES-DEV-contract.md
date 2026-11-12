# Engineering contract: SG-TABLES-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement sqlglot.report_inspection.query_copy, physical_nodes and inspect_tables(query,*,dialect=None) returning frozen TableReference(catalog,database,name,alias,quoted,scope) occurrences. Parse exactly one Query or copy supplied Query; reject empty/multiple/nonquery input. Use actual traverse_scope to exclude CTE references (including shadowing), retain physical tables inside CTE bodies, nested subqueries, self joins and SEMI/ANTI RHS. Preserve exact identifier case and catalog/db/name quote flags, scope traversal order and input AST/parent links. Ignore table functions/dynamic names rather than labeling them physical tables. Do not use regex table extraction or schema guesses.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_sg_tables_dev.py and concise English compatibility documentation at library/docs/development-sg-tables-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/sqlglot/report_inspection.py
- library/development_tests/test_development_sg_tables_dev.py
- library/docs/development-sg-tables-dev.md
