# Engineering contract: CF-OVERRIDE-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement confuse.scopes.temporary_override(root,value), a synchronous context manager for RootView and mapping dict inputs. Deep-copy input, insert one independent ConfigSource at highest priority and yield it. On normal or exceptional exit remove only that exact source identity, preserving preexisting source identities/order, unrelated additions/removals and nested scopes even when dictionaries compare equal. Do not reset the whole source list or redactions and do not claim concurrent isolation.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_cf_override_dev.py and concise English compatibility documentation at library/docs/development-cf-override-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/confuse/scopes.py
- library/development_tests/test_development_cf_override_dev.py
- library/docs/development-cf-override-dev.md
