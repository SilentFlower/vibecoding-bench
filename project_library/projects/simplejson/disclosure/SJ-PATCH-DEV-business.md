# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement simplejson.patch.apply_patch(document,operations) supporting RFC6902 add/remove/replace/move/copy/test on the completed pointer semantics. Work on a deep copy; inputs and operation values must remain unchanged on success or any later error. Array add inserts and dash appends; move resolves destination after removal and rejects moving a parent into its child. Test uses JSON equality with booleans distinct from numbers. Root replacement/add is supported and root remove returns None by explicit API convention. Missing members, invalid operations and paths fail clearly.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_sj_patch_dev.py and concise English compatibility documentation at library/docs/development-sj-patch-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/simplejson/patch.py
- library/development_tests/test_development_sj_patch_dev.py
- library/docs/development-sj-patch-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
