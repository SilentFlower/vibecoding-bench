# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add generated_sources(cls, names=None) under attr.introspection and attrs.introspection. Inspect actual current class/MRO descriptors without invoking properties or methods. Default to methods with existing attrs-generated code filenames; explicit finite unique method names also report custom/missing entries. Return nested read-only metadata generated/status/source/filename/owner, obtaining real generated source through inspect/linecache. If source is absent report unavailable; if a method is replaced report its current custom status, never stale generated source. Do not synthesize a whole class or export closure values; ordinary fields/inspect remain unchanged.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_at_generated_source_dev.py and concise English compatibility documentation at library/docs/development-at-generated-source-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/attr/introspection.py
- library/src/attrs/introspection.py
- library/development_tests/test_development_at_generated_source_dev.py
- library/docs/development-at-generated-source-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
