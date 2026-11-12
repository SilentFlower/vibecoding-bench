# Engineering contract: PA-WALK-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Path.walk_controlled(*,follow_symlinks=False,max_depth=None,exclude=(),stable=False,errors="strict"). Yield Path descendants in depth-first preorder, root depth=0; exclude relative POSIX fnmatch patterns before yielding or descending, optionally sort names per directory. Default yields links without following directory links; opted-in following tracks directory (device,inode) identities to prevent cycles/repeated subtree traversal. Respect original error handler resolution and caller Path subclass; close scandir handles, validate policies, preserve legacy walk and do not follow links implicitly.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_pa_walk_dev.py and concise English compatibility documentation at library/docs/development-pa-walk-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/path/__init__.py
- library/development_tests/test_development_pa_walk_dev.py
- library/docs/development-pa-walk-dev.md
