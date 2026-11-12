# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement werkzeug.negotiated_json.json_response(value,request,*,offers=("application/json",),status=200). Validate unique offered application/json or application/*+json media types, use actual request.accept_mimetypes.best_match for quality/specificity/wildcards, preserve offered order on ties and default first only when Accept is absent. Unacceptable including q=0 raises 406. Encode finite UTF8 JSON preserving false/null/Unicode, set selected Content-Type, exact length and Vary: Accept. Do not equate vendor JSON with plain JSON without an actual matching offer or silently emit a disallowed representation.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_wz_negotiate_dev.py and concise English compatibility documentation at library/docs/development-wz-negotiate-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/werkzeug/negotiated_json.py
- library/development_tests/test_development_wz_negotiate_dev.py
- library/docs/development-wz-negotiate-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
