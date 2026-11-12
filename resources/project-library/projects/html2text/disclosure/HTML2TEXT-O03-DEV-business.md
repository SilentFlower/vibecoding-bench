# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add figure_mode="legacy"|"group" to actual figure/figcaption/image processing. Group mode creates readable paragraph boundaries around the group, each image and each caption, preserving source order, original alt text, inline caption formatting, multiple/nested figures, caption-only/empty cases and neighboring body text. Existing ignore_images/images_to_alt/images-as-HTML behavior remains authoritative; never replace alt with caption or drop captions when images are disabled. Reset grouping depth at finish including unclosed EOF, retain default compatibility and reject unknown figure strategies.

Deliver meaningful original-failing public regression tests at library/test/test_development_html2text_o03_dev.py and concise English compatibility documentation at library/docs/development-html2text-o03-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/html2text/__init__.py
- library/test/test_development_html2text_o03_dev.py
- library/docs/development-html2text-o03-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
