# Engineering contract: CHARDET-O05-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement chardet.validated.detect_validated(data, *, validator=None). Snapshot bytes, obtain real detect_all candidates, stable-sort confidence, deduplicate supported codec aliases and strictly decode the entire payload for every candidate before an optional (text, candidate) callback. Return selected original facts and per-candidate accepted/business-rejected/decode-error/unsupported-codec statuses without returning full text. All-rejected/empty/unsupported results must not claim whole validation; callback errors propagate and confidence is never fabricated or represented as an accuracy guarantee.

Deliver meaningful original-failing public regression tests at library/tests/test_development_chardet_o05_dev.py and concise English compatibility documentation at library/docs/development-chardet-o05-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/chardet/validated.py
- library/tests/test_development_chardet_o05_dev.py
- library/docs/development-chardet-o05-dev.md
