# Engineering contract: WZ-PIPELINE-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement werkzeug.problem_middleware.ProblemMiddleware(app) composing completed problem_response and optional validated werkzeug.request_id context. Convert only HTTPException raised during app call before successful start_response into actual problem JSON, retaining original status/protocol headers and request_id extension. Other Python exceptions, HTTPException after headers started and all iterable-time errors must propagate without sending a second response. Return success iterable unchanged. Verify the real stack RequestIdMiddleware(ProblemMiddleware(app)) with bounded strict JSON input: errors and successful negotiated responses share exact request ID and native close behavior.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_wz_pipeline_dev.py and concise English compatibility documentation at library/docs/development-wz-pipeline-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/werkzeug/problem_middleware.py
- library/development_tests/test_development_wz_pipeline_dev.py
- library/docs/development-wz-pipeline-dev.md
