# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Box.get_path(path, default=NO_DEFAULT), set_path(path, value) and delete_path(path) for explicit nonempty str/int segment iterables. Distinguish integer and string keys, literal dots/brackets and list indices including negatives. Reads must not invoke box_dots parsing or create default nodes; writes require existing parents, preserve Box value conversion/recast and frozen guards, and do not create arbitrary intermediate containers. Support explicit default=None only for missing keys/indexes, propagate scalar/type errors and keep existing dotted APIs unchanged.

Deliver meaningful original-failing public regression tests at library/test/test_development_bx_path_dev.py and concise English compatibility documentation at library/docs/development-bx-path-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/box/box.py
- library/test/test_development_bx_path_dev.py
- library/docs/development-bx-path-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
