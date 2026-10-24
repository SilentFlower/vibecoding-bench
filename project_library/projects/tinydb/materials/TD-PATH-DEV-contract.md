# Engineering contract: TD-PATH-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Query.at_path(segments), appending a nonempty finite iterable of string keys to the current query path. Treat dots, slashes, empty strings and names of Query methods as literal keys. Preserve Query subclasses, immutability of the original builder, full-path cache identity and uncacheable map paths. Reject plain string/bytes inputs and nonstring segments before returning a query; preserve missing-path false behavior.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_td_path_dev.py and concise English compatibility documentation at library/docs/development-td-path-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/tinydb/queries.py
- library/development_tests/test_development_td_path_dev.py
- library/docs/development-td-path-dev.md
