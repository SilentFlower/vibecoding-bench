# Engineering contract: CK-NEW-PATH-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement click.newpath.NewPath(**Path_options) as Path with fixed exists=False/allow_dash=False, rejecting attempts to override those options. Reject existing files, directories, symlinks including dangling links, and dash before target callback; retain original path_type and resolve_path behavior for unoccupied paths. Validate both lexical input and converted path, never create/reserve targets or silently overwrite data. Preserve ordinary Path behavior and normal BadParameter exit code; document that validation is not an atomic filesystem reservation against concurrent creation.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ck_new_path_dev.py and concise English compatibility documentation at library/docs/development-ck-new-path-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/click/newpath.py
- library/development_tests/test_development_ck_new_path_dev.py
- library/docs/development-ck-new-path-dev.md
