# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add CharsetMatch.transcode(encoding="utf_8", *, errors="strict", bom="codec") returning output bytes and unencodable codepoint count. Strict must fail on unrepresentable characters; replace/ignore explicitly report losses without counting literal question marks. Support codec/strip/add BOM policy for UTF8/16/32 and reject adding unsupported BOMs. Reuse current encoding-declaration rewriting, preserve empty input and keep old output default/cache behavior independent from the new strategy.

Deliver meaningful original-failing public regression tests at library/tests/test_development_charset_normalizer_o03_dev.py and concise English compatibility documentation at library/docs/development-charset-normalizer-o03-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/charset_normalizer/models.py
- library/tests/test_development_charset_normalizer_o03_dev.py
- library/docs/development-charset-normalizer-o03-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
