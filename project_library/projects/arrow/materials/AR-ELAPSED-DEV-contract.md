# Engineering contract: AR-ELAPSED-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Arrow.elapsed(other) returning self-minus-other timedelta on the UTC timeline, and Arrow.shift_elapsed(**units) returning a new Arrow in the original zone/fold. Other must be Arrow or aware datetime; reject naive values. Fixed elapsed units are weeks/days/hours/minutes/seconds/microseconds with finite int/float values excluding booleans; reject calendar months/years and unknown units. Preserve wall-time subtraction and calendar shift unchanged. Retain exact microseconds, negative shifts, subclass construction and natural datetime overflow behavior across DST gaps/folds.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ar_elapsed_dev.py and concise English compatibility documentation at library/docs/development-ar-elapsed-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/arrow/arrow.py
- library/development_tests/test_development_ar_elapsed_dev.py
- library/docs/development-ar-elapsed-dev.md
