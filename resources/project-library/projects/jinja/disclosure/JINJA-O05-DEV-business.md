# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Extend actual compiler common import path for import/from to use Environment.get_or_select_template, preserving existing cache/module/context behavior. Accept static or dynamic ordered candidates, select first existing template and expose TemplatesNotFound for empty/all missing; an existing selected template syntax error or missing requested macro must never be swallowed as a reason to choose another candidate. Preserve string imports, aliasing, with/without context and asynchronous module handling through the actual render APIs.

Deliver meaningful original-failing public regression tests at library/tests/test_development_jinja_o05_dev.py and concise English compatibility documentation at library/docs/development-jinja-o05-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/jinja2/compiler.py
- library/tests/test_development_jinja_o05_dev.py
- library/docs/development-jinja-o05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
