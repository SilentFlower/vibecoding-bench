# Engineering contract: JM-QUERYSET-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement jmespath.queries.QuerySet(queries,*,options=None,errors="raise") and frozen QueryResult (status,value,error_type,error,phase). Compile the ordered name->expression mapping once via BoundExpression; raise is default, collect preserves individual compile/evaluate JMESPath errors while other queries continue. search(data) returns ordered name->result with phase compile/evaluate/complete and status error/passed. Do not capture unrelated programmer exceptions or retain traceback objects. Query and result-container mutations must not change later searches; standard null remains a successful None value. Use completed variadic validation and literal/option binding for reliable repeated evaluation.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_jm_queryset_dev.py and concise English compatibility documentation at library/docs/development-jm-queryset-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/jmespath/queries.py
- library/development_tests/test_development_jm_queryset_dev.py
- library/docs/development-jm-queryset-dev.md
