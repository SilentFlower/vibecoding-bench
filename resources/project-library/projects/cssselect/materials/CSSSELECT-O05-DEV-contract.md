# Engineering contract: CSSSELECT-O05-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add cssselect.formstates.FormStateTranslator(HTMLTranslator) supporting static :required and :optional. Eligible controls are select, textarea and input except hidden/range/color/button/submit/reset/image, with missing/unknown input type behaving as text and ASCII-insensitive type values. State is based on required attribute presence; disabled does not change this declaration state. The two states partition only eligible controls, not arbitrary nodes. Support unnamespaced HTML and XHTML namespace, excluding foreign same-name elements, and preserve all inherited translator APIs and GenericTranslator unsupported behavior.

Deliver meaningful original-failing public regression tests at library/tests/test_development_cssselect_o05_dev.py and concise English compatibility documentation at library/docs/development-cssselect-o05-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/cssselect/formstates.py
- library/tests/test_development_cssselect_o05_dev.py
- library/docs/development-cssselect-o05-dev.md
