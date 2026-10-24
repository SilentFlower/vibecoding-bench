# Engineering contract: BOTTLE-O06-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Build on delivered prefix cloning and add Bottle.inspect_routes() returning stable registration-order JSON metadata for actual rule/method/name/current-or-external owner, safe callback name, dynamic filter names and route-specific plugin names. Correctly explain legacy external owners and prefixed target-owned clones. Introspection must never execute callbacks, apply plugins, expose configuration/closure values or use address-bearing repr. Handle callable instances and unnamed/empty routes while preserving registration and dispatch.

Deliver meaningful original-failing public regression tests at library/test/test_development_bottle_o06_dev.py and concise English compatibility documentation at library/docs/development-bottle-o06-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/bottle.py
- library/test/test_development_bottle_o06_dev.py
- library/docs/development-bottle-o06-dev.md
