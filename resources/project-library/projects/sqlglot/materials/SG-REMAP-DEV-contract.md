# Engineering contract: SG-REMAP-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement sqlglot.report_remap.remap_tables(query,mapping,*,dialect=None,require_all=False). Reuse completed physical scope inspection; keys/values are exact (catalog,database,name) string tuples with optional empty prefixes. Quote replacement identifiers as data, never parse them as SQL. Rewrite physical named tables only, leaving CTE aliases and bodies/comments/literals otherwise compatible. Preserve existing aliases; for unaliased tables add original name as alias and repair matching scoped db/catalog-qualified columns to it. Keep table hints/other attributes. Reject malformed names and optional unused keys, return independent AST and retain source links. Do not string-replace SQL.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_sg_remap_dev.py and concise English compatibility documentation at library/docs/development-sg-remap-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/sqlglot/report_remap.py
- library/development_tests/test_development_sg_remap_dev.py
- library/docs/development-sg-remap-dev.md
