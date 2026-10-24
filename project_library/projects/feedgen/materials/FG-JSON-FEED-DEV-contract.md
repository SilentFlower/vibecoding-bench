# Engineering contract: FG-JSON-FEED-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement feedgen.json_feed.json_feed(feed) and json_feed_str(feed,*,pretty=False), following https://www.jsonfeed.org/version/1.1/ for supported fields: version/title/items, alternate/self/next links, description/language/icons/authors; item unique ID/title, inline text or HTML content, plain summary fallback, URL, aware published/modified dates, authors and enclosure attachments with MIME type/optional nonnegative byte size including zero. Require valid title/content/IDs and reject unsupported external/XHTML bodies rather than silently losing them. Return independent JSON data and UTF8 bytes, do not mutate source or invent extension mappings.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_fg_json_feed_dev.py and concise English compatibility documentation at library/docs/development-fg-json-feed-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/feedgen/json_feed.py
- library/development_tests/test_development_fg_json_feed_dev.py
- library/docs/development-fg-json-feed-dev.md
