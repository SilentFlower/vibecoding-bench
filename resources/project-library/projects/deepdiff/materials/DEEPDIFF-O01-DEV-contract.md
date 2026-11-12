# Engineering contract: DEEPDIFF-O01-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix helper.number_to_string complex precision without string-concatenating an invalid real+-imagj representation. Apply the existing recursive precision and f/e notation separately to real/imag components, reconstruct numerically preserving supported complex subclasses and existing signed-zero/nonfinite policies. Prove four quadrants, pure imaginary, zero digits, small exponents, NaN/Infinity and supported subclasses, plus actual DeepDiff/DeepHash and ignore_order paths. Keep noncomplex numeric behavior and native precision rules unchanged.

Deliver meaningful original-failing public regression tests at library/tests/test_development_deepdiff_o01_dev.py and concise English compatibility documentation at library/docs/development-deepdiff-o01-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/deepdiff/helper.py
- library/tests/test_development_deepdiff_o01_dev.py
- library/docs/development-deepdiff-o01-dev.md
