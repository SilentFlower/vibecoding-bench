# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Extend the already delivered BOM-aware RepositoryEnv with keyword-only strict=False. Strict mode rejects non-comment/nonblank lines without equals, empty trimmed keys and duplicate trimmed keys, with source path and physical one-based line number but no raw line or values in the diagnostic. Preserve UTF-8 BOM handling and embedded U+FEFF, empty values, splitting at the first equals, existing quotation handling, encoding errors and OS errors. Default tolerant skipping/last-value behavior remains unchanged; do not read unrelated files or execute shell syntax.

Deliver meaningful original-failing public regression tests at library/tests/test_development_dc_strict_env_dev.py and concise English compatibility documentation at library/docs/development-dc-strict-env-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/decouple.py
- library/tests/test_development_dc_strict_env_dev.py
- library/docs/development-dc-strict-env-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
