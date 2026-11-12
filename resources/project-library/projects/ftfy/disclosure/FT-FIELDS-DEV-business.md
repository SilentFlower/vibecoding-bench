# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement ftfy.structured.fix_fields(value,paths,config=None,*,missing="raise"), read_path and normalize_paths. Paths are explicit tuples/lists of string dict keys and nonnegative integer list indices, never dotted-string guesses; support empty root path and stable deduplication. Repair only selected text through actual fix_text, retain None and all nonselected data/keys. Return deep-copied result and leave original unchanged on any late failure. Missing keys/indices may raise or skip, type mismatches/nontext leaves always fail. Preserve caller config and original container structures.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ft_fields_dev.py and concise English compatibility documentation at library/docs/development-ft-fields-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/ftfy/structured.py
- library/development_tests/test_development_ft_fields_dev.py
- library/docs/development-ft-fields-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
