# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add tasklists_plugin(gfm_whitespace=False) as a strict boolean compatibility option. Default False must preserve the complete existing ordinary-space/tab/formfeed rendering bytes. When True, make_checkbox recognizes the same existing GFM whitespace set as starts_with_todo_markdown, including tab/vertical-tab/formfeed and repeated separators, and derives checked state from the matched space/x/X marker. Every recognized task gets exactly one actual input with matching state and original marker removal; preserve enabled/disabled and label modes. Do not broaden recognition to no-separator [x]text or non-GFM Unicode spaces, and do not merely add task CSS classes without a checkbox.

Deliver meaningful original-failing public regression tests at library/tests/test_development_mdit_plugins_o04_dev.py and concise English compatibility documentation at library/docs/development-mdit-plugins-o04-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/mdit_py_plugins/tasklists/__init__.py
- library/tests/test_development_mdit_plugins_o04_dev.py
- library/docs/development-mdit-plugins-o04-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
