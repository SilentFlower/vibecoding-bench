# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

On the delivered immutable CharsetMatch model, add stable_digest(*, mode="text", algorithm="sha256", normalization=None, text_encoding="utf-8"). Separate raw-byte and decoded-text domains, use fixed-length hashlib digests, preserve explicit encoding/newlines and default no Unicode normalization, and optionally normalize NFC/NFD/NFKC/NFKD. Same text in different source encodings must share text digests across hash-seeded processes while raw digests differ. Reject invalid modes/algorithms/raw normalization and preserve existing fingerprint.

Deliver meaningful original-failing public regression tests at library/tests/test_development_charset_normalizer_o05_dev.py and concise English compatibility documentation at library/docs/development-charset-normalizer-o05-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/charset_normalizer/models.py
- library/tests/test_development_charset_normalizer_o05_dev.py
- library/docs/development-charset-normalizer-o05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
