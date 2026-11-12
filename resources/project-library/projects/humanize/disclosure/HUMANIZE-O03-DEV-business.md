# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Extend actual natural_list(items,*,conjunction=None,serial_comma=False,localized=False) preserving byte-for-byte default English output. Consume/stringify a one-shot iterable once, correctly handle 0/1/2/many items. localized=True uses the existing real translated "%s and %s" catalog pattern; custom literal nonempty conjunction overrides it without percent-string interpretation. serial_comma is explicit for 3+ items only, with strict boolean options and Unicode/empty-string item preservation. Do not split translations/commas/connection words into separate objectives or change current activated language automatically.

Deliver meaningful original-failing public regression tests at library/tests/test_development_humanize_o03_dev.py and concise English compatibility documentation at library/docs/development-humanize-o03-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/humanize/lists.py
- library/tests/test_development_humanize_o03_dev.py
- library/docs/development-humanize-o03-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
