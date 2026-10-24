# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add opt-in keyword-only strict=False to ConfigBox bool/int/float/list and numeric/boolean aliases. Preserve default loose casting, distinguish omitted defaults from explicit default=None, and do not confuse an existing empty value with missing. Strict booleans accept bool, integer 0/1 and explicit true/false/yes/no/on/off/1/0 tokens; strict integers reject bool and truncating non-string numeric conversions; strict floats reject bool, NaN and Infinity. Strict lists accept string splitting or existing list/tuple values, apply mod once per item and report safe item positions on failure. Redact input values from strict conversion messages while retaining causes.

Deliver meaningful original-failing public regression tests at library/test/test_development_bx_strict_cast_dev.py and concise English compatibility documentation at library/docs/development-bx-strict-cast-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/box/config_box.py
- library/test/test_development_bx_strict_cast_dev.py
- library/docs/development-bx-strict-cast-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
