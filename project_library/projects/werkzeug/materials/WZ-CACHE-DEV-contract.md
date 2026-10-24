# Engineering contract: WZ-CACHE-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement werkzeug.conditional_json.cacheable_json(value,request,*,offers=("application/json",),max_age=0) using completed negotiated_json.json_response. Permit GET/HEAD only, compute strong ETag from actual selected UTF8 representation bytes, set public/max-age and reuse real Response.apply_conditions for If-None-Match/If-Match ordering and native 304/412 behavior. Retain Vary Accept and normal HEAD wire semantics. Changed representation must change ETag, matching GET/HEAD response has no wire body. Validate nonnegative integer age, preserve request and avoid reimplementing ETag comparison with substrings.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_wz_cache_dev.py and concise English compatibility documentation at library/docs/development-wz-cache-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/werkzeug/conditional_json.py
- library/development_tests/test_development_wz_cache_dev.py
- library/docs/development-wz-cache-dev.md
