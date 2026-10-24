# Engineering contract: MM-ERRORS-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement marshmallow.error_paths.flatten_errors(error) and problem(error,*,status=422,title=...). Accept real ValidationError using normalized_messages or native dict/list/string message trees; return frozen ErrorItem(pointer,messages tuple) leaves in original traversal order. Encode JSON Pointer escaping including integer array keys, retain _schema explicitly and all messages, handle root/empty errors and reject cycles/unsupported leaves. problem returns a detached status/title/errors mapping only, never exception data/valid_data or traceback. Preserve original errors and support custom field_name normalization.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_mm_errors_dev.py and concise English compatibility documentation at library/docs/development-mm-errors-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/marshmallow/error_paths.py
- library/development_tests/test_development_mm_errors_dev.py
- library/docs/development-mm-errors-dev.md
