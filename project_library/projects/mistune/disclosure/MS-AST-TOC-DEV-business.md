# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Extend add_toc_hook with include_nested=False and support renderer=None AST mode. Preserve default top-level heading selection, explicit/custom IDs, allocator collision handling and level bounds. When opted in, walk block-container descendants in source preorder; normalize AST heading display text through completed PlainTextRenderer. Expose real state.env["toc_items"] and assigned heading IDs without HTML renderer assertions. Inline normalization must use an isolated environment so collecting metadata does not register additional footnote references or mutate document plugin state.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ms_ast_toc_dev.py and concise English compatibility documentation at library/docs/development-ms-ast-toc-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/mistune/toc.py
- library/development_tests/test_development_ms_ast_toc_dev.py
- library/docs/development-ms-ast-toc-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
