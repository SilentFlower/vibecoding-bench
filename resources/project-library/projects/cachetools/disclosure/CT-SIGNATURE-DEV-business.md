# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add cachetools.keys.signature_key(func,*,typed=False,namespace=None,ignore=()), returning a key callable. Use signature.bind/apply_defaults so equivalent positional/keyword/default calls share a key, include variadic positional order and sorted variadic keywords, and optionally top-level value types (including variadic item types). Default namespace is function identity; allow explicit shared hashable namespace and explicit known ignored parameter names. Preserve binding errors and reject unhashable values without stringifying them. Do not mutate kwargs, execute the wrapped function or change existing key functions.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ct_signature_dev.py and concise English compatibility documentation at library/docs/development-ct-signature-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/cachetools/keys.py
- library/development_tests/test_development_ct_signature_dev.py
- library/docs/development-ct-signature-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
