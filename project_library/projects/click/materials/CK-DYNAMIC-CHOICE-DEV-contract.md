# Engineering contract: CK-DYNAMIC-CHOICE-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement click.dynamic.DynamicChoice(provider,*,case_sensitive=True) as ParamType. Provider accepts current Context or None and returns finite choices; snapshot once per conversion/help/completion operation and delegate actual normalization/identity/error behavior to Choice. Do not cache across calls or mutate provider results. Help metavars and shell completion must use current choices; metadata inspection must not eagerly call provider without context. Preserve original choice objects and provider exceptions, and verify independent CLI invocations with different ctx.obj values.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ck_dynamic_choice_dev.py and concise English compatibility documentation at library/docs/development-ck-dynamic-choice-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/click/dynamic.py
- library/development_tests/test_development_ck_dynamic_choice_dev.py
- library/docs/development-ck-dynamic-choice-dev.md
