# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add parse handler option namespace_collision="merge"|"error". Preserve existing merge default; error rejects when different expanded element names under the same parent or distinct expanded attributes on one element collapse to one mapped dictionary key through namespaces. Repeated identical expanded names remain valid lists, and equal local keys under separate parents are independent. Check before postprocessor transformations; do not classify ordinary repeats or user postprocessor collisions as namespace collisions. Support item_depth streaming, inherited maps and prefix remapping without global state.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_xd_namespace_collision_dev.py and concise English compatibility documentation at library/docs/development-xd-namespace-collision-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/xmltodict.py
- library/development_tests/test_development_xd_namespace_collision_dev.py
- library/docs/development-xd-namespace-collision-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
