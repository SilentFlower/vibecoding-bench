# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Extend only the builtin regex format registration to catch declared regular-expression compilation failures: re.error, ValueError for incompatible inline flags, RecursionError for bounded deeply nested patterns and OverflowError for repeat limits. FormatChecker.check must produce FormatError retaining cause and real format validation must yield ValidationError instead of leaking those failures. Preserve empty/valid patterns and nonstring JSON Schema format semantics. Never catch arbitrary BaseException or broaden unrelated custom checker programming-error handling.

Deliver meaningful original-failing public regression tests at library/tests/test_development_jsonschema_o04_dev.py and concise English compatibility documentation at library/docs/development-jsonschema-o04-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/jsonschema/_format.py
- library/tests/test_development_jsonschema_o04_dev.py
- library/docs/development-jsonschema-o04-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
