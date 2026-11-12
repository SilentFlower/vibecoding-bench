# Engineering contract: IF-RULES-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement inflect.rules.define_nouns(engine,rules) using the completed independent engine clone. Each rule mapping has singular/plural and optional case, no unknown keys. Use real defnoun validation and precedence including regex/case policies; later valid rules override as normal. Validate and apply the entire iterable on a clone before committing any state to the original. Invalid pattern, case, rule shape or generator exception leaves all original state unchanged. Return accepted count and retain unrelated custom verbs/articles/options. Do not parse or execute rule text as Python.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_if_rules_dev.py and concise English compatibility documentation at library/docs/development-if-rules-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/inflect/rules.py
- library/development_tests/test_development_if_rules_dev.py
- library/docs/development-if-rules-dev.md
