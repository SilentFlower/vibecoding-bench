# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Extend BaseAdmonition directives with collapsible/expanded flags, rejecting expanded without collapsible. Preserve actual admonition/title/body nodes and existing localized specific-admonition transforms. HTML5 writer emits native details/summary, optional open, original inline formatting/escaping and correct nested pairs without JS; ordinary prompts remain on the original aside path. Other writers keep full visible text. Do not remove collapsed body, duplicate titles, mutate global visitor behavior or treat input raw HTML as trusted output.

Deliver meaningful original-failing public regression tests at library/tests/test_development_docutils_o04_dev.py and concise English compatibility documentation at library/docs/development-docutils-o04-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/docutils/docutils/parsers/rst/directives/admonitions.py
- library/docutils/docutils/writers/html5_polyglot/__init__.py
- library/tests/test_development_docutils_o04_dev.py
- library/docs/development-docutils-o04-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
