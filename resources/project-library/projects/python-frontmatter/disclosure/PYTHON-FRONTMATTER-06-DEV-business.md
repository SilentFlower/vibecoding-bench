# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add frontmatter.atomic.atomic_update(path, transform, encoding="utf-8", expected_sha256=None) and UpdateConflict for an existing regular file. Strictly validate frontmatter using parse_result, read with the binary-stream loading ability, call transform once with a fresh Post and require a returned Post. Render and encode before touching the target. Use a same-directory temporary, preserve mode/owner, flush+fsync, then os.replace. Clean temporary files and preserve original bytes for every failure before replace. Reject symlink targets, expected-version mismatch and changes observed during the transform before commit; do not claim a lock-free check is a linearizable compare-and-swap against uncooperative external writers. Preserve the already delivered compact/nested JSON, TOML format, reserved metadata, Unicode and body. Missing/malformed documents and transform/encoding/IO failures remain explicit. This is a complete safe-edit API, not just a utility-test step.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_frontmatter_06_dev.py, and English compatibility documentation at library/docs/development-python-frontmatter-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/frontmatter/atomic.py
- library/tests/test_development_python_frontmatter_06_dev.py
- library/docs/development-python-frontmatter-06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
