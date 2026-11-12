# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add optional attribute_provider=None to DictExporter. A callable receives each visited node and returns a mapping or finite key/value iterable. Use only explicitly supplied fields, then apply existing attriter/dictcls; never enumerate arbitrary slots or properties. Exclude parent/children and NodeMixin/LightNodeMixin structural private fields from provider results. Require string attribute keys, propagate provider errors, preserve maxlevel/childiter and ordinary __dict__ export. Support LightNodeMixin-only slots nodes and normal DictImporter round trips without hidden structure leakage.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_an_slots_dev.py and concise English compatibility documentation at library/docs/development-an-slots-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/anytree/exporter/dictexporter.py
- library/development_tests/test_development_an_slots_dev.py
- library/docs/development-an-slots-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
