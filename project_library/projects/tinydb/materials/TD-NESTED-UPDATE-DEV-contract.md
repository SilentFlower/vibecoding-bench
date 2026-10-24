# Engineering contract: TD-NESTED-UPDATE-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add tinydb.operations.set_path(path,value,*,create=False) and delete_path(path,*,missing_ok=False), returning ordinary Table.update callbacks. Paths are finite nonempty string-key sequences with literal punctuation. Set deep-copies the supplied value when building the operation and separately per document; optionally create missing mapping parents. Delete preserves siblings and optionally tolerates missing keys. Nonmapping parents remain errors. Validate a complete candidate document before replacing that document contents so a failed callback leaves it unchanged; do not promise a transaction across all documents or modify old operations.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_td_nested_update_dev.py and concise English compatibility documentation at library/docs/development-td-nested-update-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/tinydb/operations.py
- library/development_tests/test_development_td_nested_update_dev.py
- library/docs/development-td-nested-update-dev.md
