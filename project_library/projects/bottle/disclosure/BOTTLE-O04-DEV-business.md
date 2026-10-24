# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add BaseResponse.charset setter that validates a real codec before mutating Content-Type, replaces all case-insensitive/quoted charset parameters with one selected charset and preserves media type and unrelated parameters including quoted semicolons. Getter must read quoted/case-insensitive parameters correctly. Real Bottle string output must use the selected encoding; bytes behavior and direct content_type assignment remain unchanged. Invalid/empty codecs leave headers intact.

Deliver meaningful original-failing public regression tests at library/test/test_development_bottle_o04_dev.py and concise English compatibility documentation at library/docs/development-bottle-o04-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/bottle.py
- library/test/test_development_bottle_o04_dev.py
- library/docs/development-bottle-o04-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
