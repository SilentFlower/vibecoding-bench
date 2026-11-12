# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement marshmallow.unique.UniqueList(inner,*,key=None,**kwargs) as a true List field. Run normal inner deserialization first, then uniqueness on resulting values or a callable projection. Support unhashable keys without stringification; bool differs from numeric values. Report every later duplicate at its input index with first-occurrence context, preserve valid_data and native inner errors/required/allow_none. Keep standard serialization. Repeated schema instances must not share bound inner fields or per-call observations.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_mm_unique_dev.py and concise English compatibility documentation at library/docs/development-mm-unique-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/marshmallow/unique.py
- library/development_tests/test_development_mm_unique_dev.py
- library/docs/development-mm-unique-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
