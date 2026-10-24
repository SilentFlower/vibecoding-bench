# Engineering contract: FEEDPARSER-O02-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Complete actual JSON1.1 adapter metadata: ordered authors arrays with name/url/avatar mapped to authors details, first author compatibility fields, feed/item language and detached item inheritance when absent. Explicit authors=[] suppresses author inheritance, and authors takes precedence over legacy author; retain existing single-author behavior. Validate array/member/string shapes and nonempty language explicitly so original parse bozo reports malformed data rather than silently dropping it. Preserve actual raw content/date handling, no new network or invented language inference.

Deliver meaningful original-failing public regression tests at library/tests/test_development_feedparser_o02_dev.py and concise English compatibility documentation at library/docs/development-feedparser-o02-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/feedparser/parsers/json.py
- library/tests/test_development_feedparser_o02_dev.py
- library/docs/development-feedparser-o02-dev.md
