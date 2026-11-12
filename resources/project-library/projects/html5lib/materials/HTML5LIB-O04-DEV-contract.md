# Engineering contract: HTML5LIB-O04-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add diagnostics.parse_with_report using the actual HTMLParser and returning tree/errors/encoding/compat_mode/truncated. Collect structured real position/code/details errors, support first-error policy through original strict ParseError and ignore policy hiding reports, and cap report entries with explicit truncation without mislabeling it a parsing resource budget. Preserve namespace/backend/encoding kwargs and ordinary html5lib.parse behavior; recovered trees remain equivalent, valid documents do not gain errors and invalid options reject before parsing. Do not invent source spans or suppress strict failures as successful output.

Deliver meaningful original-failing public regression tests at library/tests/test_development_html5lib_o04_dev.py and concise English compatibility documentation at library/docs/development-html5lib-o04-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/html5lib/diagnostics.py
- library/tests/test_development_html5lib_o04_dev.py
- library/docs/development-html5lib-o04-dev.md
