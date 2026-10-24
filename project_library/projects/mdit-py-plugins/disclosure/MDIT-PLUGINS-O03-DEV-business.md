# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix tasklists_plugin(label=True, label_after=True) to wrap existing parsed inline children with a paired label after the checkbox, never popping a content/closing token or reinserting raw Markdown as HTML. Preserve rich emphasis/link/image/multiline content exactly once, HTML-disabled escaping, matching generated id/for, nested list structure and enabled/disabled checkbox behavior. Default no-label and ordinary wrapping-label modes remain unchanged. Do not flatten parsed children to unescaped text or merely hide duplicated output.

Deliver meaningful original-failing public regression tests at library/tests/test_development_mdit_plugins_o03_dev.py and concise English compatibility documentation at library/docs/development-mdit-plugins-o03-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/mdit_py_plugins/tasklists/__init__.py
- library/tests/test_development_mdit_plugins_o03_dev.py
- library/docs/development-mdit-plugins-o03-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
