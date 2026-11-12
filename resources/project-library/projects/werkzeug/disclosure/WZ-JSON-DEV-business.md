# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement werkzeug.strict_json.read_json(request,*,max_bytes=1048576). Require actual JSON mimetype including application/*+json and UTF8 charset, enforce positive byte budget against declared and actual stream size using at most max_bytes+1 read. Respect Werkzeug WSGI stream termination rules. Decode UTF8, reject nested duplicate keys after escape decoding, nonfinite constants and float overflow; invalid syntax/encoding/empty input becomes BadRequest, unsupported media 415 and budget overflow 413. Return any valid JSON value including false/null. This consumes the stream; do not modify legacy get_json cache, globals, body limits or close caller-owned input.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_wz_json_dev.py and concise English compatibility documentation at library/docs/development-wz-json-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/werkzeug/strict_json.py
- library/development_tests/test_development_wz_json_dev.py
- library/docs/development-wz-json-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
