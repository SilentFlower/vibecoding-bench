# Engineering contract: PT-TRANSFORM-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add IntervalDict.transform_values(function, *, pass_interval=False) returning the same concrete class without mutating the source. Call once per stored (possibly composite) interval/value entry in order, optionally passing (value, interval). Only identity with IntervalDict.DROP deletes an entry; None and unhashable values are legitimate. Rebuild through existing normalization so equal outputs merge correctly. Preserve domain except dropped entries, propagate callback exceptions and retain custom IntervalDict subclasses.

Deliver meaningful original-failing public regression tests at library/tests/test_development_pt_transform_dev.py and concise English compatibility documentation at library/docs/development-pt-transform-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/portion/dict.py
- library/tests/test_development_pt_transform_dev.py
- library/docs/development-pt-transform-dev.md
