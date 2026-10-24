# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Repair union disambiguation so dataclass default_factory fields are treated as optional using the actual adapted field defaults, without invoking factories during discrimination. Truly ambiguous unions must raise TypeError independently of member order instead of selecting the class with the factory field. Preserve real required unique fields, ordinary defaults, attrs factories, Literal/renaming overrides and every frozen regression.

Deliver meaningful original-failing public regression tests at library/tests/test_development_cattrs_o01_dev.py and concise English compatibility documentation at library/docs/development-cattrs-o01-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/cattrs/disambiguators.py
- library/tests/test_development_cattrs_o01_dev.py
- library/docs/development-cattrs-o01-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
