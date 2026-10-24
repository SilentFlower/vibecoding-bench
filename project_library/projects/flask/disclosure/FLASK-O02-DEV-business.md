# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add App.validate_routes() returning structured overlap/missing_view/view_signature diagnostics using actual url_map/view_functions without invoking views. Report identical rule/host/subdomain overlaps in non-HEAD/OPTIONS methods, missing runtime views and inspect.signature(...).bind mismatches for actual route/default arguments. Ignore build_only, preserve wrapped signatures, optional args/**kwargs/MethodView and skip uninspectable callables or signature claims when url-value preprocessors may alter arguments. Do not speculate about intersection of different converter patterns or change default route registration/dispatch; this is explicit API inspection, not an unimplemented CLI.

Deliver meaningful original-failing public regression tests at library/tests/test_development_flask_o02_dev.py and concise English compatibility documentation at library/docs/development-flask-o02-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/flask/sansio/app.py
- library/tests/test_development_flask_o02_dev.py
- library/docs/development-flask-o02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
