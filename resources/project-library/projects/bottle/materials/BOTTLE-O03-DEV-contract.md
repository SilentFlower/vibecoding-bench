# Engineering contract: BOTTLE-O03-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Extend Bottle.merge(routes, prefix=None). None must preserve legacy route identity/owner. An explicit absolute prefix clones routes with target ownership, copied route-specific plugins/skip/config and original callback, normalizes trailing slashes and supports dynamic built-in filters/reverse URLs without changing source rules. Target app plugin policy applies to clones, source app plugins are not implicitly copied. Reject bad prefixes and duplicate route names before adding any clones; preserve original source registration and callback behavior.

Deliver meaningful original-failing public regression tests at library/test/test_development_bottle_o03_dev.py and concise English compatibility documentation at library/docs/development-bottle-o03-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/bottle.py
- library/test/test_development_bottle_o03_dev.py
- library/docs/development-bottle-o03-dev.md
