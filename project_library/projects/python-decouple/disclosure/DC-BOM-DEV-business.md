# Delivery and verification boundaries

Make RepositoryEnv and RepositoryIni accept an optional UTF-8 BOM only at the start of a UTF-8 encoded file, including standard UTF-8 codec aliases and utf-8-sig. Handle empty/BOM-only files and a BOM before a comment. Preserve every later U+FEFF in keys or values, existing Config precedence/casts/defaults, explicitly requested non-UTF8 encodings, and decoding errors. Apply the policy at the actual repository file-reading boundaries, not by global string replacement or modifying os.environ.

Deliver source changes and public regressions rather than an investigation report alone. Investigate and propose a plan, obtain confirmation, and implement in the same original conversation. Rework actual reported failures. Check original failures, reference passes, and the complete frozen upstream regression separately; reference results do not count as model results.
