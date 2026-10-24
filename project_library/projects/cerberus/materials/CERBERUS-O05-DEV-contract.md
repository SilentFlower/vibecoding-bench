# Engineering contract: CERBERUS-O05-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Validator.validate_result(document, schema=None, *, update=False, normalize=True) and frozen-shell cerberus.result.ValidationResult(valid, document, errors, completed=True). Run actual validation and deep-copy normalized document plus the configured error_handler output so later calls and result-content mutations cannot overwrite validator/other results. Preserve validate/validated bool/None interfaces and normalization/update flags. Unexpected exceptions propagate without publishing a completed result; document that nested snapshot contents are editable and the validator is not made thread safe.

Deliver meaningful original-failing public regression tests at library/tests/test_development_cerberus_o05_dev.py and concise English compatibility documentation at library/docs/development-cerberus-o05-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/cerberus/validator.py
- library/cerberus/result.py
- library/tests/test_development_cerberus_o05_dev.py
- library/docs/development-cerberus-o05-dev.md
