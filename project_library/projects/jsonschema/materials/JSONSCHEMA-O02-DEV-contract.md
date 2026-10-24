# Engineering contract: JSONSCHEMA-O02-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix _Error.json_path dot-safe identification with full-string matching and correct single-quoted bracket escaping for quote/backslash and every C0 control character. A key x followed by LF must never render as $.x plus a raw LF or resolve to the separate key x. Preserve ordinary ASCII identifier dot notation, Unicode/empty bracket keys, array indexes, original path values and absolute parent-path composition. Demonstrate independent decoding/selection round trips rather than only comparing a hard-coded diagnostic string.

Deliver meaningful original-failing public regression tests at library/tests/test_development_jsonschema_o02_dev.py and concise English compatibility documentation at library/docs/development-jsonschema-o02-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/jsonschema/exceptions.py
- library/tests/test_development_jsonschema_o02_dev.py
- library/docs/development-jsonschema-o02-dev.md
