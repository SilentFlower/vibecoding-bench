# Engineering contract: MDIT-PLUGINS-O06-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add optional callback(record) to anchors_plugin and the actual core anchor assignment path. Invoke once per selected heading after final unique slug assignment, supplying title before permalink injection, final slug, integer level and an independent map list or None. Callback records must match real rendered ids for duplicate titles/custom slug functions; changing a record/map must not mutate Token state. Keep default behavior, selected-level filtering and per-document uniqueness, do not repeat callback when rendering already parsed tokens, and propagate consumer exceptions explicitly. Do not simulate navigation by reparsing rendered HTML.

Deliver meaningful original-failing public regression tests at library/tests/test_development_mdit_plugins_o06_dev.py and concise English compatibility documentation at library/docs/development-mdit-plugins-o06-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/mdit_py_plugins/anchors/index.py
- library/tests/test_development_mdit_plugins_o06_dev.py
- library/docs/development-mdit-plugins-o06-dev.md
