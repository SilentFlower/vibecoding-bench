# Engineering contract: CERBERUS-O01-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Repair rename identity and combined rename/rename_handler normalization. rename to the same field must preserve its value; when both rules are present, apply the handler to the explicit rename target and move the original value only after the final name is resolved. Keep handler failure diagnostics and original value, caller input isolation and existing overwrite-target policy. Preserve standalone rename/handler, nested normalization and frozen upstream controls; do not silently drop fields or raise KeyError from an already removed old key.

Deliver meaningful original-failing public regression tests at library/tests/test_development_cerberus_o01_dev.py and concise English compatibility documentation at library/docs/development-cerberus-o01-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/cerberus/validator.py
- library/tests/test_development_cerberus_o01_dev.py
- library/docs/development-cerberus-o01-dev.md
