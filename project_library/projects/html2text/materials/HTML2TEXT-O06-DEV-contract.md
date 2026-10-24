# Engineering contract: HTML2TEXT-O06-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add public immutable Options.from_mapping with declared body_width and common link/image/wrapping switches, and HTML2Text.from_options(options, *, out=None, baseurl="") integrated through the actual constructor/property conversion path. Reject unknown keys, nonbool switches, bool/noninteger/negative widths, conflicting image rendering modes and single_line_break with nonzero width in this explicit strict mode. Options detach input, expose independent as_dict copies and are reusable across independent converters. Preserve ordinary construction/dynamic property assignments, default byte output, custom out and baseurl. This task covers API strict configuration; do not claim unimplemented CLI integration or globally forbid legacy combinations.

Deliver meaningful original-failing public regression tests at library/test/test_development_html2text_o06_dev.py and concise English compatibility documentation at library/docs/development-html2text-o06-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/html2text/__init__.py
- library/test/test_development_html2text_o06_dev.py
- library/docs/development-html2text-o06-dev.md
