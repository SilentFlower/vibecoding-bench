# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement bidict.readonly.ReadOnlyBidictProxy as a read-only BidirectionalMapping with live forward/inverse lookups, stable inverse.inverse identity and inv alias. Preserve source order and live views after additions/deletions/clear, reject mutation in either direction and do not expose writable source through ordinary views. copy() returns an independent frozen snapshot. Preserve None, accept existing bidirectional subclasses and document that values are not deeply frozen and concurrency is not isolated.

Deliver meaningful original-failing public regression tests at library/tests/test_development_bidict_o06_dev.py and concise English compatibility documentation at library/docs/development-bidict-o06-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/bidict/readonly.py
- library/tests/test_development_bidict_o06_dev.py
- library/docs/development-bidict-o06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
