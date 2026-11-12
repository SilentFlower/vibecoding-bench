# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement cattrs.strategies.pathlike.configure_pathlike(converter, *, factory=Path) for PathLike and PathLike[str] annotations through actual predicate hooks. Unstructure using os.fspath and require str output, structure only str through an explicit factory returning text PathLike, reject byte paths/invalid factory returns without implicit decoding. Support nested JSON records and custom __fspath__, never touch the filesystem, and preserve concrete Path defaults and converter isolation.

Deliver meaningful original-failing public regression tests at library/tests/test_development_cattrs_o05_dev.py and concise English compatibility documentation at library/docs/development-cattrs-o05-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/cattrs/strategies/pathlike.py
- library/tests/test_development_cattrs_o05_dev.py
- library/docs/development-cattrs-o05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
