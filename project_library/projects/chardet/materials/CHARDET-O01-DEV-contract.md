# Engineering contract: CHARDET-O01-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Repair UniversalDetector startup to buffer only incomplete possible BOM prefixes until a complete UTF8/16/32 or unusual UCS4 BOM can be distinguished, then use existing detection semantics. Handle UTF16-vs-UTF32 prefix overlap, arbitrary byte/empty chunks, near-prefix mismatches, EOF partial prefixes and reset reuse without losing or duplicating bytes. Ordinary non-BOM input must start probing immediately; preserve original labels, confidence, all probers and frozen upstream tests.

Deliver meaningful original-failing public regression tests at library/tests/test_development_chardet_o01_dev.py and concise English compatibility documentation at library/docs/development-chardet-o01-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/chardet/universaldetector.py
- library/tests/test_development_chardet_o01_dev.py
- library/docs/development-chardet-o01-dev.md
