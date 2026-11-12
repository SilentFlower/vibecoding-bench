# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement sqlglot.report_binding.parameter_names(tree) and bind_parameters(query,values,*,strict=True,dialect=None) on completed single-query copies. Replace named Placeholder nodes with real exp literal conversions, repeated uses get independent nodes; literals/comments/identifiers containing colon text stay unchanged. Support None/bool/int/finite float/finite Decimal/str/bytes/date/time/datetime and recursive lists, reject nonfinite/cyclic/unsupported objects and SQL Expr values. Missing parameters always fail; strict rejects extras, nonstrict ignores unused values. Reject positional placeholders explicitly and preserve original AST parents. Never parse parameter text as SQL.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_sg_bind_dev.py and concise English compatibility documentation at library/docs/development-sg-bind-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/sqlglot/report_binding.py
- library/development_tests/test_development_sg_bind_dev.py
- library/docs/development-sg-bind-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
