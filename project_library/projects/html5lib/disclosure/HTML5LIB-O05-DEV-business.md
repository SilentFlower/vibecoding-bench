# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add text.extract_text(tree,*,treewalker="etree",include_hidden=False,include_images=False) using actual backend walker events. Preserve reading/tail order, paragraph and br boundaries, ordered/unordered list markers, decoded entities and exact pre-internal spaces/newlines while collapsing ordinary HTML whitespace. Omit head/script/style body-irrelevant text; hidden/template are optional and explicit image alt may be included. DOM/etree produce equivalent text and input trees/serializer output remain unchanged. Do not simply concatenate Characters, drop tail or claim HTML sanitization/network fetching.

Deliver meaningful original-failing public regression tests at library/tests/test_development_html5lib_o05_dev.py and concise English compatibility documentation at library/docs/development-html5lib-o05-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/html5lib/text.py
- library/tests/test_development_html5lib_o05_dev.py
- library/docs/development-html5lib-o05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
