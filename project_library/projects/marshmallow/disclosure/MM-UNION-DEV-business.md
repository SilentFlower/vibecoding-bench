# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement marshmallow.discriminated.DiscriminatedNested(discriminator,schemas,**kwargs) as a Field. schemas is a nonempty mapping of nonempty string tags to real Schema instances. Select by external discriminator, remove that tag before selected schema.load/dump(many=False), then restore it; do not mutate input. Preserve selected nested errors/unknown policy and partial propagation. Missing or unknown tags produce structured ValidationError at the tag. Schema outputs must be mappings not occupying the external tag; allow_none and normal field lifecycle still work. Do not guess schema variants.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_mm_union_dev.py and concise English compatibility documentation at library/docs/development-mm-union-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/marshmallow/discriminated.py
- library/development_tests/test_development_mm_union_dev.py
- library/docs/development-mm-union-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
