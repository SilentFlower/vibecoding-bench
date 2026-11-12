# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add webcolors.css_rgb.parse_css_rgb and serialize_css_rgb, using RGBA byte semantics from the prior goal. Support legacy rgb(r,g,b)/rgba(r,g,b,a) with all-number or all-percent channels and modern rgb()/rgba() three whitespace-separated channels with optional / alpha. Modern channels may mix numeric and percent; numeric exponent syntax is allowed if finite. Clamp RGB/alpha to their range then round to nearest byte with halves up. Reject mixed separators, partial suffixes, missing components, NaN/Inf, none, calc/var and unsupported expressions. Serializer uses stable modern syntax and roundtrips every alpha byte without loss. Keep existing name/hex/HTML parsers untouched and document the deliberately supported subset.

Deliver real implementation, original-failing public tests at library/tests/test_development_webcolors_04_dev.py, and English compatibility documentation at library/docs/development-webcolors-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/webcolors/css_rgb.py
- library/tests/test_development_webcolors_04_dev.py
- library/docs/development-webcolors-04-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
