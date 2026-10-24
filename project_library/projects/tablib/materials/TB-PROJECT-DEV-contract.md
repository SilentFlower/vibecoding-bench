# Engineering contract: TB-PROJECT-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement tablib.projection.select_columns(dataset,columns,*,rename=None) plus schema/copy_rows/key_token helpers for later table operations. Require actual Dataset with nonempty unique string headers and consistent stored widths. Select/reorder nonempty unique existing names, validate rename output collisions, deep-copy stored cells/title/row tags and leave source unchanged. The result is explicitly a static data snapshot: dynamic cells keep current stored values and dynamic definitions/export formatters/separators are not copied or executed. key_token uses strict type-and-value hashable keys, so bool/int/float are distinct; fail clearly on mutable keys.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_tb_project_dev.py and concise English compatibility documentation at library/docs/development-tb-project-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/tablib/projection.py
- library/development_tests/test_development_tb_project_dev.py
- library/docs/development-tb-project-dev.md
