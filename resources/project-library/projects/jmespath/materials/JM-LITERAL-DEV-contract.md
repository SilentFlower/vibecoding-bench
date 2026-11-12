# Engineering contract: JM-LITERAL-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix TreeInterpreter.visit_literal so mutable JSON literal results cannot mutate the cached parsed expression or later searches. Deeply detach object/array literal nodes on each evaluation, including literals nested in multi-select/projections and custom functions. Preserve scalar literal values, input field identity semantics, parser cache use and existing equality/type rules. Do not deepcopy every input document or purge compilation caches as a workaround.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_jm_literal_dev.py and concise English compatibility documentation at library/docs/development-jm-literal-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/jmespath/visitor.py
- library/development_tests/test_development_jm_literal_dev.py
- library/docs/development-jm-literal-dev.md
