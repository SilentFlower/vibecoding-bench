# Engineering contract: JSONSCHEMA-O06-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add FormatChecker.compose(format, checker, *, mode="all", raises=()) for an existing registered format on this instance only, returning self. Combine the captured prior checker and new callable in order with all/any short circuit, preserving declared input-exception causes in FormatError and propagating undeclared programming errors. Keep original checks decorator overwrite semantics and independent/global checker registries unchanged. Reject unknown formats, invalid mode/callable/raises before mutation. Exercise actual builtin date syntax plus business conditions through FormatChecker and a real JSON Schema format keyword; no global monkeypatch or duplicated fake validation.

Deliver meaningful original-failing public regression tests at library/tests/test_development_jsonschema_o06_dev.py and concise English compatibility documentation at library/docs/development-jsonschema-o06-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/jsonschema/_format.py
- library/tests/test_development_jsonschema_o06_dev.py
- library/docs/development-jsonschema-o06-dev.md
