# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement sqlglot.report.prepare_report(query,*,values=None,tables=None,max_rows=None,offset=0,read=None,write=None) returning frozen PreparedReport(sql,tables,output_columns,parameters). Compose completed inspection/remap/bind/bounds APIs: parse once, require every supplied table mapping to match, bind every named parameter strictly, capture output projection names before optional outer limit and inspect final actual physical tables. Retain original unique parameter names and compile to requested dialect. No unresolved named placeholders or silent extras, offset requires bounds. Preserve supplied AST and do not execute SQL or fabricate schema/lineage.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_sg_report_dev.py and concise English compatibility documentation at library/docs/development-sg-report-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/sqlglot/report.py
- library/development_tests/test_development_sg_report_dev.py
- library/docs/development-sg-report-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
