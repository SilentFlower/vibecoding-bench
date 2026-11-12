# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add HTMLRenderer keyword-only url_rewriter=None. For actual rendered link/image tokens, call (original_url,"link"|"image") once and require a string return; then run the existing sanitize_url and attribute escaping on the rewritten URL. Preserve visible link text, image alt/title, nested emphasis, reference links and auto links. Default output and raw HTML remain unchanged; callback exceptions propagate and a rewritten javascript URL must not bypass the existing harmful-protocol policy.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ms_url_rewrite_dev.py and concise English compatibility documentation at library/docs/development-ms-url-rewrite-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/mistune/renderers/html.py
- library/development_tests/test_development_ms_url_rewrite_dev.py
- library/docs/development-ms-url-rewrite-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
