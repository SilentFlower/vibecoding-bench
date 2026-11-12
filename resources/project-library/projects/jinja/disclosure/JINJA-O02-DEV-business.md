# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix CodeGenerator.visit_Include synchronous without-context handling so buffered macro/set/filter frames append real included events via simple_write, instead of making the macro return a generator representation. Preserve top-level streaming, actual without-context isolation, nested macros, ignore missing, autoescape and existing async parity. Do not silently switch to with context or reevaluate include arguments; demonstrate concrete rendered output through actual compilation/render/generate paths.

Deliver meaningful original-failing public regression tests at library/tests/test_development_jinja_o02_dev.py and concise English compatibility documentation at library/docs/development-jinja-o02-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/jinja2/compiler.py
- library/tests/test_development_jinja_o02_dev.py
- library/docs/development-jinja-o02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
