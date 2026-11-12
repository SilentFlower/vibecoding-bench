# Engineering contract: DYNACONF-O03-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix Settings.update to copy its top-level mapping/standard dict-constructor input before merging kwargs, preserving kwargs precedence and all actual parsing/validation paths. Ordinary and read-only mappings, empty mappings and iterable pairs work; successful or validation-failed updates never add/overwrite keys in caller input. Do not introduce arbitrary deepcopy, silently promise nested ownership/transaction rollback, change settings partial-update semantics or bypass validators.

Deliver meaningful original-failing public regression tests at library/tests/test_development_dynaconf_o03_dev.py and concise English compatibility documentation at library/docs/development-dynaconf-o03-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/dynaconf/base.py
- library/tests/test_development_dynaconf_o03_dev.py
- library/docs/development-dynaconf-o03-dev.md
