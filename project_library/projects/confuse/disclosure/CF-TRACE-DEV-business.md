# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement confuse.trace.trace_sources(view,*,include_values=False,redact=True) returning immutable SourceTrace records in actual view.resolve order. Records contain filename/default/base_for_paths, kind of resolved value, zero-based priority, is_first and optional value. Missing views produce an empty tuple; first means first resolution, not sole contributor to merged dictionaries. Default mode must not expose values. Included values use the completed snapshot freeze logic and relative redactions including sequences, remain detached, and reject unsupported/cyclic structures. No file reads or source mutations.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_cf_trace_dev.py and concise English compatibility documentation at library/docs/development-cf-trace-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/confuse/trace.py
- library/development_tests/test_development_cf_trace_dev.py
- library/docs/development-cf-trace-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
