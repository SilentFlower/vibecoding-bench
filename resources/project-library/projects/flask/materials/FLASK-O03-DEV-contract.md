# Engineering contract: FLASK-O03-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Config.validate(constraints) explicit lightweight nonmutating validation returning aggregated {path:[keys],code} diagnostics for required/type/nullable/choices/minimum/maximum/properties. Missing and None differ; reject bool as int/float unless bool explicitly allowed, preserve literal dotted keys and recurse only through explicit properties. Existing loading/dict semantics remain unchanged and values are never converted or included in diagnostics. Correct configurations pass unchanged; invalid rule fields/types raise configuration errors rather than guessing a schema or leaking values. Do not broaden this into HTTP request validation.

Deliver meaningful original-failing public regression tests at library/tests/test_development_flask_o03_dev.py and concise English compatibility documentation at library/docs/development-flask-o03-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/flask/config.py
- library/tests/test_development_flask_o03_dev.py
- library/docs/development-flask-o03-dev.md
