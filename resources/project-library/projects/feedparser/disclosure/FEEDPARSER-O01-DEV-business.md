# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix JSONParser.parse_entry date_modified detection/value consistency through actual feedparser.parse. Preserve the original date string and UTC parsed tuple, prefer correct date_modified when both spellings exist and explicitly support legacy date_updated only as fallback without KeyError. Missing modified dates must not create real updated keys from published aliases; invalid strings remain raw with parsed None. Do not replace published or merely rely on FeedParserDict compatibility fallback to claim a modified date exists.

Deliver meaningful original-failing public regression tests at library/tests/test_development_feedparser_o01_dev.py and concise English compatibility documentation at library/docs/development-feedparser-o01-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/feedparser/parsers/json.py
- library/tests/test_development_feedparser_o01_dev.py
- library/docs/development-feedparser-o01-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
