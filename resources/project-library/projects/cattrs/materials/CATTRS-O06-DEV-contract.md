# Engineering contract: CATTRS-O06-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement cattrs.strategies.sequence_union.configure_sequence_union(converter, union) as opt-in actual union-hook registration for exactly one list/tuple/Sequence branch and one attrs/dataclass/dict record branch. Mapping input selects the record, non-text Sequence selects the sequence, then delegate every nested conversion to current converter hooks. Support empty/tuple input and nested custom hooks, reject text/bytes/generators and ambiguous branch sets explicitly, and leave other union/default behavior unchanged.

Deliver meaningful original-failing public regression tests at library/tests/test_development_cattrs_o06_dev.py and concise English compatibility documentation at library/docs/development-cattrs-o06-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/cattrs/strategies/sequence_union.py
- library/tests/test_development_cattrs_o06_dev.py
- library/docs/development-cattrs-o06-dev.md
