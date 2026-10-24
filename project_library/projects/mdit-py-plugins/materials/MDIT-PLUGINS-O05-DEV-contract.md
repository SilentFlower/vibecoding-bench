# Engineering contract: MDIT-PLUGINS-O05-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix _front_matter_rule to check the current scanned line for the existing triple-dot terminator, consuming it exactly once while excluding it from token.content and including it in the half-open token.map. Closing at EOF, empty metadata and trailing horizontal whitespace must work and preserve the first body line. Keep existing dash delimiters, initial-document-only recognition, insufficient/open-without-close fallback and hidden/block/markup behavior. Four dots or noninitial blocks must not be silently accepted as metadata.

Deliver meaningful original-failing public regression tests at library/tests/test_development_mdit_plugins_o05_dev.py and concise English compatibility documentation at library/docs/development-mdit-plugins-o05-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/mdit_py_plugins/front_matter/index.py
- library/tests/test_development_mdit_plugins_o05_dev.py
- library/docs/development-mdit-plugins-o05-dev.md
