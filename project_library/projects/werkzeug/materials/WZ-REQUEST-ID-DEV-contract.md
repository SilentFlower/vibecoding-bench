# Engineering contract: WZ-REQUEST-ID-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement werkzeug.request_id.RequestIdMiddleware(app,*,factory=None). Accept incoming X-Request-ID only when it matches ASCII [A-Za-z0-9][A-Za-z0-9._-]{0,63}, otherwise generate a UUID hex or injected factory value and validate it. Store werkzeug.request_id in environ and emit exactly one matching X-Request-ID response header, replacing application duplicates case-insensitively. Forward status, all other repeated headers, start_response exc_info and write return unchanged. Return original app iterable without pre-reading/wrapping so close and streaming/backpressure remain native. Propagate app errors; do not trust multiline header input or silently accept invalid factory results.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_wz_request_id_dev.py and concise English compatibility documentation at library/docs/development-wz-request-id-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/werkzeug/request_id.py
- library/development_tests/test_development_wz_request_id_dev.py
- library/docs/development-wz-request-id-dev.md
