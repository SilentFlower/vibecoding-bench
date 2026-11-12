# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix deepcopy(Section/ConfigObj) to copy raw stored values rather than interpolated items. Preserve same concrete types, raw expressions, nested list expressions, comments/default metadata and internal parent/main graph links using the deepcopy memo. Cached interpolation engines must bind to the cloned sections. Copies must independently recalculate after root/nested changes; creating a copy must not trigger interpolation loops. Preserve the explicit evaluated semantics of Section.dict(), ordinary retrieval and existing pickle behavior.

Deliver meaningful original-failing public regression tests at library/tests/test_development_configobj_o01_dev.py and concise English compatibility documentation at library/docs/development-configobj-o01-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/configobj/__init__.py
- library/tests/test_development_configobj_o01_dev.py
- library/docs/development-configobj-o01-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
