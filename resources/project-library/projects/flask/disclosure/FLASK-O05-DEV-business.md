# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add JSONProvider.stream(values) returning the application response class with application/x-ndjson, lazily invoking this actual provider.dumps once per consumed value in compact single physical lines plus newline. Preserve custom provider encoding, Unicode/newline escaping and request context through stream_with_context when a request is active. Do not materialize the iterable; response close/failure/normal exhaustion closes its source once, including unstarted close. Empty input works; unsupported or multiline provider output terminates with an explicit error. Document that a late failure after first bytes cannot revise HTTP status, and leave jsonify array behavior unchanged.

Deliver meaningful original-failing public regression tests at library/tests/test_development_flask_o05_dev.py and concise English compatibility documentation at library/docs/development-flask-o05-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/flask/json/provider.py
- library/tests/test_development_flask_o05_dev.py
- library/docs/development-flask-o05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
