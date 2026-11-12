# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement feedgen.publish.write_feed(feed,destination,*,format="atom",pretty=False) and frozen FeedArtifact(format,size,sha256). Serialize entire actual Atom/RSS or completed JSON Feed to UTF8 before touching target, preserve completed Atom link metadata including zero-length string values. Write same-dir temp, flush/fsync and atomic replace; retain existing regular file permissions. Invalid feed, serialization/write/replace failure must retain old file and remove temp. Reject unknown formats and symlink/nonfile output, return exact final byte count/hash only on success. Do not reimplement XML or drop registered extensions, and do not claim multiple feed files publish as one transaction.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_fg_publish_dev.py and concise English compatibility documentation at library/docs/development-fg-publish-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/feedgen/publish.py
- library/development_tests/test_development_fg_publish_dev.py
- library/docs/development-fg-publish-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
