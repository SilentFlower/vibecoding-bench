# Engineering contract: AP-FORMAT-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix configuration._format_input_factory to validate nested format-spec fields and conversions before the progress renderer starts. Permit only the existing allowed field names and conversions None/s/r/a at every parsed level, reject malformed braces, attribute/index traversal, unknown nested names and nested replacement depth beyond Formatter supported nesting. Preserve literal/escaped braces, valid dynamic width references and all existing bool/nonstring handling; return existing ERROR sentinel for invalid formats rather than deferring failures to a background render.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ap_format_dev.py and concise English compatibility documentation at library/docs/development-ap-format-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/alive_progress/core/configuration.py
- library/development_tests/test_development_ap_format_dev.py
- library/docs/development-ap-format-dev.md
