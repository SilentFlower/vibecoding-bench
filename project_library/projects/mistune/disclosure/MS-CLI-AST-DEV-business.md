# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Support existing CLI --renderer ast by serializing the actual list of token dictionaries as UTF8 JSON on stdout or --output. Preserve input priority, explicit/piped empty documents as [], source Unicode, nested token attributes and configured plugins; do not stringify Python repr or wrap JSON in HTML. Existing html/markdown/rst/version behavior and file/stdout side effects stay compatible. Use the completed empty-document fix as prerequisite; errors still yield a nonzero process status.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ms_cli_ast_dev.py and concise English compatibility documentation at library/docs/development-ms-cli-ast-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/mistune/__main__.py
- library/development_tests/test_development_ms_cli_ast_dev.py
- library/docs/development-ms-cli-ast-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
