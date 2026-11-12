# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement chardet.transcode.transcode_bytes(data, target_encoding, *, source_encoding=None). Use the explicit source codec or actual detection result, require a supported codec and strict full-payload decoding/encoding with no replacement or character loss. Return independent output bytes, canonical source/target names, original detection facts when used and validated byte count. Target codec explicitly controls BOM, empty auto-detection must request a source, unrepresentable target text and malformed source bytes fail, and input buffers remain unchanged. Do not imply autodetected semantic accuracy.

Deliver meaningful original-failing public regression tests at library/tests/test_development_chardet_o06_dev.py and concise English compatibility documentation at library/docs/development-chardet-o06-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/chardet/transcode.py
- library/tests/test_development_chardet_o06_dev.py
- library/docs/development-chardet-o06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
