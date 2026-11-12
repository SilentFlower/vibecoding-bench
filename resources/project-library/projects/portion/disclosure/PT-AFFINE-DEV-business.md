# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Interval.affine(scale, offset=0) and translate(offset) for continuous intervals. Positive scales preserve bounds, negative scales swap endpoints and openness, zero maps every nonempty input to a singleton and empty remains empty. Preserve disjoint pieces, infinity direction, Decimal arithmetic and concrete continuous subclasses; reject nonfinite/NaN parameters and explicitly reject AbstractDiscreteInterval images that cannot generally be represented as continuous intervals. Do not change subtraction, replace or apply semantics.

Deliver meaningful original-failing public regression tests at library/tests/test_development_pt_affine_dev.py and concise English compatibility documentation at library/docs/development-pt-affine-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/portion/interval.py
- library/tests/test_development_pt_affine_dev.py
- library/docs/development-pt-affine-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
