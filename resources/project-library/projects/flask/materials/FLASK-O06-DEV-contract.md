# Engineering contract: FLASK-O06-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix real App.add_url_rule endpoint conflict ordering so a conflicting different view is rejected before mutating url_map or view_functions. After catching AssertionError, the proposed new URL must remain 404 and previous rules/views/methods/defaults/matcher behavior exactly match preattempt state. Preserve identical-view aliases, view_func=None later binding, automatic methods, blueprint-qualified endpoints and existing exception text. Do not hide conflicts, delete the existing view, rebuild the entire map or alter frozen tests.

Deliver meaningful original-failing public regression tests at library/tests/test_development_flask_o06_dev.py and concise English compatibility documentation at library/docs/development-flask-o06-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/flask/sansio/app.py
- library/tests/test_development_flask_o06_dev.py
- library/docs/development-flask-o06-dev.md
