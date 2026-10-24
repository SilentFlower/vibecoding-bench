# Engineering contract: ICECREAM-O06-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add icecream.builtins.managed_install(name="ic",debugger=None) and already-installed BuiltinInstallation handle/context, leaving original install/uninstall unchanged. Record previous value and ownership tokens, restore/remove only when the current binding still belongs to this installation, and leave foreign replacements untouched. Support same/different debugger nested installs, idempotent and out-of-order close without resurrecting closed ancestors, exception cleanup and rejection of closed reentry/invalid identifiers/keywords/wrong debugger. Never scan other builtins; all verification uses synthetic names, not print or production globals.

Deliver meaningful original-failing public regression tests at library/tests/test_development_icecream_o06_dev.py and concise English compatibility documentation at library/docs/development-icecream-o06-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/icecream/builtins.py
- library/tests/test_development_icecream_o06_dev.py
- library/docs/development-icecream-o06-dev.md
