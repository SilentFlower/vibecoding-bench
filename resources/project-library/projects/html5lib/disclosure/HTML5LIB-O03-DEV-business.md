# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add public html5lib.tokenizer.iter_tokens wrapping the actual internal HTMLTokenizer, yielding detached dictionaries with named token types and real production-time (line,column) checkpoints. Preserve data/attributes/entities/comments/Doctype and optional ParseError inclusion, stream encoding kwargs and caller stream ownership. A nonnegative max_tokens output budget raises TokenLimitError on overflow rather than pretending partial output is complete; bool/invalid budgets reject, empty input works and early close is safe. Do not label lexer events as repaired DOM nodes or fabricate exact start spans from end checkpoints.

Deliver meaningful original-failing public regression tests at library/tests/test_development_html5lib_o03_dev.py and concise English compatibility documentation at library/docs/development-html5lib-o03-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/html5lib/tokenizer.py
- library/tests/test_development_html5lib_o03_dev.py
- library/docs/development-html5lib-o03-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
