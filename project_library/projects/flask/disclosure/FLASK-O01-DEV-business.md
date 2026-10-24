# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Extend actual flask routes CLI with --format table|json (default table), --endpoint exact name and --blueprint registered-name prefix including nested blueprints. JSON is one versioned object {schema:1,routes:[...]}, including endpoint/rule/sorted full methods/host/subdomain/defaults/automatic_options, honoring sort and empty apps/filters without terminal prose. Convert bounded native JSON defaults without executing opaque repr; unknown values use {$type: class_name}. Preserve ordinary table output, existing --all-methods and matching order semantics; use actual url_map metadata and do not invoke views.

Deliver meaningful original-failing public regression tests at library/tests/test_development_flask_o01_dev.py and concise English compatibility documentation at library/docs/development-flask-o01-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/flask/cli.py
- library/tests/test_development_flask_o01_dev.py
- library/docs/development-flask-o01-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
