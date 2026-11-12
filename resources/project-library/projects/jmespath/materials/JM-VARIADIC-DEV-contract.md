# Engineering contract: JM-VARIADIC-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix Functions._type_check so every actual variadic argument uses the final signature rule after the fixed prefix. Preserve arity validation, array subtype checking, untyped variadic rules and custom function dispatch. Invalid later values must raise JMESPathTypeError before calling the function body, with actual function/type context; do not rely on uncontrolled Python exceptions from merge or custom functions. Fixed-arity behavior and all language semantics remain compatible.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_jm_variadic_dev.py and concise English compatibility documentation at library/docs/development-jm-variadic-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/jmespath/functions.py
- library/development_tests/test_development_jm_variadic_dev.py
- library/docs/development-jm-variadic-dev.md
