# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add mutating Box.rename_key(old, new) returning self. Rename a literal existing key at exactly its original insertion position, preserve value/sub-Box identity and configuration without recasting or reconversion, and update safe-attribute lookup. Reject missing old keys, existing targets, protected attributes, safe-alias collisions and frozen mutation before changing any data; old==new is an unchanged success for mutable boxes. Preserve integer keys and ordinary assignment semantics.

Deliver meaningful original-failing public regression tests at library/test/test_development_bx_rename_dev.py and concise English compatibility documentation at library/docs/development-bx-rename-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/box/box.py
- library/test/test_development_bx_rename_dev.py
- library/docs/development-bx-rename-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
