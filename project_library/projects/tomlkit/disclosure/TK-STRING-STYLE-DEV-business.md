# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add String.replace_value(value,*,fallback=False), returning a detached String that retains original single/multiline and basic/literal quote kind and an independent copy of trivia. Encode semantic value through existing from_raw so escaped characters and leading multiline newlines roundtrip. If literal style cannot represent the value, propagate InvalidStringError unless fallback=True, then switch only to the matching-width basic style. Preserve original node and str.replace semantics; validate arguments.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_tk_string_style_dev.py and concise English compatibility documentation at library/docs/development-tk-string-style-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/tomlkit/items.py
- library/development_tests/test_development_tk_string_style_dev.py
- library/docs/development-tk-string-style-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
