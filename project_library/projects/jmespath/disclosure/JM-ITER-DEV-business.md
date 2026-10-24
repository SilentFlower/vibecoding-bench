# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement jmespath.streaming.iter_search(expression,documents,*,options=None,errors="raise"). Compile/bind once before consuming first document and yield one result per consumed document without prefetching. Default returns raw standard values; collect returns (zero_based_index,QueryResult) for each success or JMESPath evaluation error using the completed result schema. Syntax errors always raise before input consumption, source/programmer errors propagate, stopping/closing iteration reads no further documents, and independent literal results remain detached. Never materialize whole streams.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_jm_iter_dev.py and concise English compatibility documentation at library/docs/development-jm-iter-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/jmespath/streaming.py
- library/development_tests/test_development_jm_iter_dev.py
- library/docs/development-jm-iter-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
