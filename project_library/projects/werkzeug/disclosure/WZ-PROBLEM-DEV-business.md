# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement werkzeug.problems.problem_response(error,*,type="about:blank",instance=None,extensions=None) for real HTTPException. Create a NEW Response with actual error status, type/title/status/detail and optional instance/extensions, UTF8 finite JSON, application/problem+json and exact content length. Retain original protocol headers including duplicate Set-Cookie, Allow, WWW-Authenticate and Retry-After; replace only representation headers appropriately. Do not mutate a response supplied inside the exception. Reject reserved extension collisions/non-string keys and non-error status. Do not turn unrelated Python exceptions into successful HTTP responses.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_wz_problem_dev.py and concise English compatibility documentation at library/docs/development-wz-problem-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/werkzeug/problems.py
- library/development_tests/test_development_wz_problem_dev.py
- library/docs/development-wz-problem-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
