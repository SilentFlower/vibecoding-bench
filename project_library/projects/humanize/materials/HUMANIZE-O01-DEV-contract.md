# Engineering contract: HUMANIZE-O01-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix i18n translation cache identity to include locale plus resolved catalog root, including PathLike/relative aliases, using actual GNUTranslations bytes. Extend activate(locale,path=None,*,reload=False) with explicit per-source reload that bypasses gettext stale cache without clearing unrelated sources. Load before changing current state; failure preserves prior selection. Preserve default English/None/deactivate and explicit legacy default _TRANSLATIONS injection, but never let injected/default locale objects shadow an explicit different directory. Demonstrate synthetic real GNU catalogs, source reuse, reload, failure and separator compatibility.

Deliver meaningful original-failing public regression tests at library/tests/test_development_humanize_o01_dev.py and concise English compatibility documentation at library/docs/development-humanize-o01-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/humanize/i18n.py
- library/tests/test_development_humanize_o01_dev.py
- library/docs/development-humanize-o01-dev.md
