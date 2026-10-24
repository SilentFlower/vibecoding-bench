# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Extend actual dynaconf list CLI with repeatable --match glob patterns over top-level canonical key names, case-insensitive union without duplicates. Apply after existing env/loader selection on a detached dictionary and consistently to text/JSON/output-file views; empty matches return valid empty data, not a fake missing-key failure. Reject combining --match with old --key explicitly while preserving legacy no-pattern/single-key behavior. Use fnmatch semantics, never arbitrary eval/regex rewriting, and do not mutate settings or loader history during filtering.

Deliver meaningful original-failing public regression tests at library/tests/test_development_dynaconf_o06_dev.py and concise English compatibility documentation at library/docs/development-dynaconf-o06-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/dynaconf/cli.py
- library/tests/test_development_dynaconf_o06_dev.py
- library/docs/development-dynaconf-o06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
