# Engineering contract: MDIT-PLUGINS-O01-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix attrs_plugin(spans=True, allowed=...) so _span_rule receives and applies the same _add_attrs filtering policy as supported links/images/code. Keep only allowed attributes on the real opening Token and rendered HTML while preserving rejected attributes in insecure_attrs metadata. None remains unrestricted and an empty sequence forbids all. Preserve nested spans, quoted attributes, parsing fallback and existing non-span filtering; do not disable spans or discard all attributes to pass the examples.

Deliver meaningful original-failing public regression tests at library/tests/test_development_mdit_plugins_o01_dev.py and concise English compatibility documentation at library/docs/development-mdit-plugins-o01-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/mdit_py_plugins/attrs/index.py
- library/tests/test_development_mdit_plugins_o01_dev.py
- library/docs/development-mdit-plugins-o01-dev.md
