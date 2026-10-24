# Engineering contract: HUMANIZE-O06-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add humanize.percent.naturalpercent(value,*,input_unit="ratio",precision=1,rounding="half_even",group=False,space=""). Require explicit ratio/percent unit, finite int/float/Decimal excluding bool/text, 0..28 non-bool precision and half_even/half_up/down. Scale/quantize with sufficiently precise local Decimal context without float conversion or global context mutation; normalize rounded negative zero. Use actual current humanize decimal/thousands separators, optional grouping and literal percent spacing, preserving existing number formatters. Prove half-value rounding, huge finite integers/Decimal, negative/zero/out-of-unit-range values, strict options and locale output.

Deliver meaningful original-failing public regression tests at library/tests/test_development_humanize_o06_dev.py and concise English compatibility documentation at library/docs/development-humanize-o06-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/humanize/percent.py
- library/tests/test_development_humanize_o06_dev.py
- library/docs/development-humanize-o06-dev.md
