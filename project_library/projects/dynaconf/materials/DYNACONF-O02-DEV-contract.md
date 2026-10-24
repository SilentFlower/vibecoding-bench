# Engineering contract: DYNACONF-O02-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix Validator.validate when-environment inheritance as call-local evaluation context, never persisting an inferred env list onto shared self.when. Respect explicit child envs, nested when/and/or and only_current_env while retaining normal validation behavior. A descriptor first used by disabled dev must still reject negative PORT when enabled prod is checked, exactly as a fresh descriptor would. Concurrent/nested instances must not leak environments or require deepcopy of arbitrary user predicates; reset context on every failure/return.

Deliver meaningful original-failing public regression tests at library/tests/test_development_dynaconf_o02_dev.py and concise English compatibility documentation at library/docs/development-dynaconf-o02-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/dynaconf/validator.py
- library/tests/test_development_dynaconf_o02_dev.py
- library/docs/development-dynaconf-o02-dev.md
