# Engineering contract: BA-PREFERENCES-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add babel.core.negotiate_locale_preferences(header, available, *, sep="_", aliases=LOCALE_ALIASES). Parse bounded comma-separated language ranges and optional q values 0..1 with at most three decimals. Select descending quality, stable header order; reuse pinned negotiate_locale matching/aliases for each nonwildcard candidate and return spelling from available. Explicit q=0 language/prefix exclusions must apply before wildcard selection; wildcard picks first nonexcluded available. Reject malformed parameters, quality, headers over 8192 characters or 100 ranges. Materialize available once and preserve the old negotiator.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ba_preferences_dev.py and concise English compatibility documentation at library/docs/development-ba-preferences-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/babel/core.py
- library/development_tests/test_development_ba_preferences_dev.py
- library/docs/development-ba-preferences-dev.md
