# Engineering contract: CATTRS-O04-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement cattrs.strategies.strict.configure_strict_primitives(converter, *, allow_int_float=False, finite_float=True). Opt in exact bool/int/float/str/bytes input types without coercion, reject bool as int and primitive subclasses, explicitly control int-to-float and nonfinite float policy. Apply through actual registered hooks so nested containers/records retain cattrs validation paths. Keep unconfigured converters, unstructure behavior and later user-hook overrides intact.

Deliver meaningful original-failing public regression tests at library/tests/test_development_cattrs_o04_dev.py and concise English compatibility documentation at library/docs/development-cattrs-o04-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/cattrs/strategies/strict.py
- library/tests/test_development_cattrs_o04_dev.py
- library/docs/development-cattrs-o04-dev.md
