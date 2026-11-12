# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement dpath.walking.walk_paths(root,*,include_containers=False,cycles="error",max_depth=None,max_nodes=None), yielding (tuple_path,original_value) in mapping/list source preorder. Root depth zero and node budget includes root/containers. Empty containers are leaves; optional nonempty containers are emitted too. Track active ancestors iteratively: PathCycleError.path identifies cycles or skip drops only cyclic edges, while shared acyclic objects appear under both paths. Reject invalid budgets, bound before yielding offending nodes, avoid Python recursion and preserve original path key types/input.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_dp_walk_dev.py and concise English compatibility documentation at library/docs/development-dp-walk-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/dpath/walking.py
- library/development_tests/test_development_dp_walk_dev.py
- library/docs/development-dp-walk-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
