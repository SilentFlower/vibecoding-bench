# Engineering contract: CSSSELECT-O01-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement cssselect.compiled.compile_selector(css, *, mode="xml", xhtml=False, prefix="descendant-or-self::") returning frozen CompiledSelector with canonical tuple, per-branch specificity tuple, XPath, mode, xhtml and prefix. Parse the complete real selector group once, never split literal commas, use actual selector_to_xpath with pseudo-element rejection and retain original exceptions. Support XML/HTML/XHTML casing and explicit prefixes, reject invalid mode/type combinations. Store no mutable parse tree or bound document and add no lxml runtime dependency; callers can evaluate the same XPath against multiple actual trees.

Deliver meaningful original-failing public regression tests at library/tests/test_development_cssselect_o01_dev.py and concise English compatibility documentation at library/docs/development-cssselect-o01-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/cssselect/compiled.py
- library/tests/test_development_cssselect_o01_dev.py
- library/docs/development-cssselect-o01-dev.md
