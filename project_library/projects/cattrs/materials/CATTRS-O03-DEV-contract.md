# Engineering contract: CATTRS-O03-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement cattrs.strategies.base64.configure_base64(converter, *, urlsafe=False) with paired bytes hooks on the supplied real converter. Support nested existing JSON converters, empty/all-byte payloads and explicitly selected URL-safe alphabet. Strictly reject bad padding, non-ASCII and invalid characters, never guess formats or affect unconfigured base85 defaults. Later user hooks remain higher priority and non-string structure input fails clearly.

Deliver meaningful original-failing public regression tests at library/tests/test_development_cattrs_o03_dev.py and concise English compatibility documentation at library/docs/development-cattrs-o03-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/cattrs/strategies/base64.py
- library/tests/test_development_cattrs_o03_dev.py
- library/docs/development-cattrs-o03-dev.md
