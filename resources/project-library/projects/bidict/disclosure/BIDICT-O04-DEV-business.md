# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement bidict.relation_patch.relation_diff(before, after) and apply_relation_patch(mapping, patch, *, reverse=False). Produce versioned explicit add/remove/reassign facts with ordered full pre/post relations; apply only when the complete expected current relation/order matches. Validate final key/value uniqueness and return a new same-type relation, allowing cyclic value swaps, additions/removals and exact reverse restoration. Preserve original inputs on stale conditions, malformed schema or invalid final relations; never execute operation strings.

Deliver meaningful original-failing public regression tests at library/tests/test_development_bidict_o04_dev.py and concise English compatibility documentation at library/docs/development-bidict-o04-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/bidict/relation_patch.py
- library/tests/test_development_bidict_o04_dev.py
- library/docs/development-bidict-o04-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
