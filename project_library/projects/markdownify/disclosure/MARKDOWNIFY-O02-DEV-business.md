# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add opt-in task_lists conversion in actual convert_li. A task checkbox is exclusively the first direct non-whitespace/non-comment content node, an input whose type is case-insensitive checkbox; checked attribute presence means checked regardless of attribute text. Emit [x]/[ ] after existing unordered or ordered bullet, retaining empty tasks, nested list ownership and multiline indentation. Default conversion remains unchanged. Never infer parent tasks from descendant labels/lists or later inputs, and never interpret other input types as checkboxes.

Deliver meaningful original-failing public regression tests at library/tests/test_development_markdownify_o02_dev.py and concise English compatibility documentation at library/docs/development-markdownify-o02-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/markdownify/__init__.py
- library/tests/test_development_markdownify_o02_dev.py
- library/docs/development-markdownify-o02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
