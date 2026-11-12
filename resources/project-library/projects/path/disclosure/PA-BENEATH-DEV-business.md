# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Path.relative_beneath(base), normalizing absolute lexical paths then requiring commonpath containment and returning relative Path of the caller class. Same path returns "."; sibling prefix collisions and normalized .. escapes reject with ValueError, including cross-drive errors from the path module. Do no filesystem reads, symlink resolution or existence checks. Preserve original relpath and clearly distinguish this lexical operation from a symlink-safe containment/security boundary.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_pa_beneath_dev.py and concise English compatibility documentation at library/docs/development-pa-beneath-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/path/__init__.py
- library/development_tests/test_development_pa_beneath_dev.py
- library/docs/development-pa-beneath-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
