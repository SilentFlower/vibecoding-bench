# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add humanize.context.locale_scope(locale,path=None) / LocaleScope using ContextVar, the accepted source-aware real catalog loader and context-local translation plus decimal/thousands separators. Deterministically interleaved asyncio tasks must keep distinct same-locale catalogs; nested default-English scopes override thread state and restore outer state on exceptions/cancellation. Do not mutate global/other-task thread selections; legacy activate/deactivate remains thread-local and is hidden while an explicit scope is active. Reject active same-instance reentry, load failures leave context unchanged and permit sequential reuse after exit.

Deliver meaningful original-failing public regression tests at library/tests/test_development_humanize_o02_dev.py and concise English compatibility documentation at library/docs/development-humanize-o02-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/humanize/i18n.py
- library/src/humanize/context.py
- library/tests/test_development_humanize_o02_dev.py
- library/docs/development-humanize-o02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
