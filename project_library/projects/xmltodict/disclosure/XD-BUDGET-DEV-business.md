# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add optional parse kwargs max_depth/max_elements/max_text_chars (None or nonnegative nonboolean integer), validated before consuming input. Count depth including root=1, all element starts and cumulative decoded character-data lengths including whitespace (not attributes/comments). Raise XMLLimitError(ValueError) before constructing the offending element or appending excess text. Bound whole input even in item_depth streaming, namespace and chunked modes. Preserve unlimited defaults, entity blocking and callback stop semantics; do not claim rollback of callbacks emitted before a later limit failure.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_xd_budget_dev.py and concise English compatibility documentation at library/docs/development-xd-budget-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/xmltodict.py
- library/development_tests/test_development_xd_budget_dev.py
- library/docs/development-xd-budget-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
