# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair Heading.content so every ATX heading retains its own raw inline source after later headings or documents are parsed. Preserve empty/enclosed headings, children, instance assignment, HTML output and the existing AST/repr schema. Separate parser scratch state from per-node content; do not change frozen tests or serialize an extra Heading content field.

Deliver real implementation, original-failing public tests at library/tests/test_development_mistletoe_01_dev.py, and English compatibility documentation at library/docs/development-mistletoe-01-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/mistletoe/block_token.py
- library/tests/test_development_mistletoe_01_dev.py
- library/docs/development-mistletoe-01-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
