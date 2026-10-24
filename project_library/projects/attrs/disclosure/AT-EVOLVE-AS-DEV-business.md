# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add evolve_as(instance, target_class, **changes) in attr.evolution and attrs.evolution. Copy common init=True fields by their real attribute names into the target initialization aliases, with explicit target-alias changes winning. Use the target standard constructor so its converters, defaults/factories, validators and post-init execute normally. Do not copy init=False hidden state, mutate the source or deep-copy existing payloads. Reject unknown target aliases, alias conflicts, non-attrs types and unrelated targets with no common init fields; leave missing required arguments and target validation errors explicit. Preserve ordinary attrs.evolve.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_at_evolve_as_dev.py and concise English compatibility documentation at library/docs/development-at-evolve-as-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/attr/evolution.py
- library/src/attrs/evolution.py
- library/development_tests/test_development_at_evolve_as_dev.py
- library/docs/development-at-evolve-as-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
