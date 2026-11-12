# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add DateTimeParser.parse_match(text, format_or_list, normalize_whitespace=False) returning immutable ParsedDateTimeMatch with value datetime, selected format, original span/matched/prefix/suffix and a separate normalized_span. Select the earliest calendar-valid match across formats, breaking equal-position ties by format order; skip invalid dates and empty/literal-only matches. Preserve raw Unicode and whitespace exactly. If whitespace is normalized for matching, map every matched normalized character back to its original span rather than pretending normalized indices refer to raw input. Use the complete strict token parser and preserve old parse return types and boundaries.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ar_match_dev.py and concise English compatibility documentation at library/docs/development-ar-match-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/arrow/parser.py
- library/development_tests/test_development_ar_match_dev.py
- library/docs/development-ar-match-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
