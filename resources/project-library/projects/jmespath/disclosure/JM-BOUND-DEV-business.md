# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement jmespath.bound.BoundExpression(expression,options=None) with read-only expression and search(data,options=sentinel). Compile once, snapshot Options dict_cls/custom_functions references at binding so later mutation of the Options container does not change defaults, and create the normal interpreter per call. Omitted override uses binding, explicit None uses standard defaults, explicit Options affects one call. Retain custom function object identity, actual parser/errors and input field semantics; require completed literal isolation so callers cannot poison repeated template results.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_jm_bound_dev.py and concise English compatibility documentation at library/docs/development-jm-bound-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/jmespath/bound.py
- library/development_tests/test_development_jm_bound_dev.py
- library/docs/development-jm-bound-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
