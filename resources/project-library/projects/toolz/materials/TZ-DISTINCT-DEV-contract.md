# Engineering contract: TZ-DISTINCT-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Repair isdistinct for reiterable data sources that implement __iter__ but no length protocol. Scan once, stop at the first duplicate and preserve hashability/error semantics. Keep the existing sized-sequence fast path, propagate errors from a genuinely implemented __len__ or iterator, and do not read a second iterator or consume unreachable tails. Preserve iterators, lists, empty input and exported namespaces.

Deliver meaningful original-failing public regression tests at library/toolz/tests/test_development_tz_distinct_dev.py and concise English compatibility documentation at library/docs/development-tz-distinct-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/toolz/itertoolz.py
- library/toolz/tests/test_development_tz_distinct_dev.py
- library/docs/development-tz-distinct-dev.md
