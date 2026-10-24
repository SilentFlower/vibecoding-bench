# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Extend the delivered PathLike-aware template lookup: give MakoTemplate/Jinja2Template/CheetahTemplate their own engine suffixes ahead of existing legacy extensions, and allow BaseTemplate instances to append explicit extensions without mutating parent or other instances. Extend search to accept an explicit extension sequence used by initialization; preserve PathLike names/directories, direct filename search, lookup priority and legacy .tpl fallback. Validate bad path-like suffixes and prove SimpleTemplate actually renders an instance-only extension without requiring optional engines.

Deliver meaningful original-failing public regression tests at library/test/test_development_bottle_o02_dev.py and concise English compatibility documentation at library/docs/development-bottle-o02-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/bottle.py
- library/test/test_development_bottle_o02_dev.py
- library/docs/development-bottle-o02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
