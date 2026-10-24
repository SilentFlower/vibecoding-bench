# Engineering contract: MARKDOWNIFY-O05-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Extend actual convert_hN with heading_offset (integer, default zero), heading_minimum (integer 1..6, default one), and heading_overflow clamp/bold/error (default clamp). Map depth to max(minimum, original_depth+offset) before choosing Setext or ATX style; clamp at six, render a normalized bold paragraph, or raise for overflow according to the explicit policy. Reject bool/noninteger offsets and invalid minima/policies. Preserve existing default rendering, nonstandard hN handling, empty bold overflow and existing inline table/heading contexts. This is a real document-level hierarchy conversion, not post-hoc string substitution.

Deliver meaningful original-failing public regression tests at library/tests/test_development_markdownify_o05_dev.py and concise English compatibility documentation at library/docs/development-markdownify-o05-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/markdownify/__init__.py
- library/tests/test_development_markdownify_o05_dev.py
- library/docs/development-markdownify-o05-dev.md
