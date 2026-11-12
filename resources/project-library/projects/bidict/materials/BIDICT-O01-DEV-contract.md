# Engineering contract: BIDICT-O01-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement bidict.compose.compose(mapping, other, *, missing="error") for two BidirectionalMapping inputs. Compose A->B and B->C into a validated same-concrete-type A->C mapping, preserving left order and both sources. Missing intermediate keys either raise or explicitly select intersection with missing="ignore". Support inverse symmetry, None, empty/frozen/ordered inputs and reject invalid policies/non-bidirectional sources; do not change union or putall semantics.

Deliver meaningful original-failing public regression tests at library/tests/test_development_bidict_o01_dev.py and concise English compatibility documentation at library/docs/development-bidict-o01-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/bidict/compose.py
- library/tests/test_development_bidict_o01_dev.py
- library/docs/development-bidict-o01-dev.md
