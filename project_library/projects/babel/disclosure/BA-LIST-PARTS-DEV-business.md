# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add babel.lists.format_list_to_parts(lst, style="standard", locale=None). Return ordered dictionaries with type element/literal, exact value, and original input index or None. Concatenation must equal format_list for all supported CLDR styles, fallback styles and locales, including repeated/empty strings, braces and Unicode. Do not locate elements by searching formatted text or use collision-prone sentinels. Preserve input and format_list.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ba_list_parts_dev.py and concise English compatibility documentation at library/docs/development-ba-list-parts-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/babel/lists.py
- library/development_tests/test_development_ba_list_parts_dev.py
- library/docs/development-ba-list-parts-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
