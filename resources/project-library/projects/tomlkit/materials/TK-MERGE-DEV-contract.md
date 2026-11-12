# Engineering contract: TK-MERGE-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement tomlkit.merging.merge_documents(base,overlay,*,arrays="replace",conflicts="replace"). Deep-copy base, recursively merge mapping children, and choose explicit replace/append/unique for arrays (including arrays of tables, using native value equality for uniqueness). Copy incoming mutable nodes, preserve unaffected base comments/layout and validate the final serialized TOML. conflicts="error" rejects differing scalar/type conflicts without changing either input. Reject unknown policies/nonmapping overlay; preserve existing parse/dumps behavior and do not infer merges from implicit global settings.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_tk_merge_dev.py and concise English compatibility documentation at library/docs/development-tk-merge-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/tomlkit/merging.py
- library/development_tests/test_development_tk_merge_dev.py
- library/docs/development-tk-merge-dev.md
