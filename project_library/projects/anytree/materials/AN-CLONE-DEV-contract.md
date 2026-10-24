# Engineering contract: AN-CLONE-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add anytree.util.clone_subtree(node, *, factory=None, copy_attributes=None). Traverse children iteratively and clone __dict__-backed nodes into new AnyNode instances by default, preserving order and all nonstructural attributes. Default attribute payload copying is shallow; an explicit callable can choose deep copy or filtering and must return a mapping without structural fields. An optional kwargs factory can preserve a desired node class but must return distinct detached empty NodeMixin/LightNodeMixin nodes, never original nodes. Validate every result before attaching copies. Do not clone external parents or traverse symbolic targets. Reject repeated/cyclic structure and unsupported slots-only source nodes explicitly; preserve the source tree.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_an_clone_dev.py and concise English compatibility documentation at library/docs/development-an-clone-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/anytree/util/clone.py
- library/src/anytree/util/__init__.py
- library/development_tests/test_development_an_clone_dev.py
- library/docs/development-an-clone-dev.md
