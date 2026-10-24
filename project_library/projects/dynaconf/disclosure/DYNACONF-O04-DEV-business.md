# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Extend validated Settings.load_file with format=None|json|toml|yaml and thread it into settings_loader. Explicit mode overrides suffix discovery and skips Python-module guessing, using whitelisted existing readers through real BaseLoader with actual file paths/source metadata, environment/key filtering, merge/validation/hooks contracts. Reject unknown or disabled core loaders; syntax errors stay visible under existing semantics. Default extension discovery remains unchanged; do not copy files to fake suffixes, import arbitrary format strings or treat a filename as serialized config text.

Deliver meaningful original-failing public regression tests at library/tests/test_development_dynaconf_o04_dev.py and concise English compatibility documentation at library/docs/development-dynaconf-o04-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/dynaconf/base.py
- library/dynaconf/loaders/__init__.py
- library/tests/test_development_dynaconf_o04_dev.py
- library/docs/development-dynaconf-o04-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
