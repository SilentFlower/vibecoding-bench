# Support a leading UTF-8 BOM in configuration files while preserving real values

Pinned source: https://github.com/HBNetwork/python-decouple @ 0573e6f96637f08fb4cb85e0552f0622d36827d4.

Make RepositoryEnv and RepositoryIni accept an optional UTF-8 BOM only at the start of a UTF-8 encoded file, including standard UTF-8 codec aliases and utf-8-sig. Handle empty/BOM-only files and a BOM before a comment. Preserve every later U+FEFF in keys or values, existing Config precedence/casts/defaults, explicitly requested non-UTF8 encodings, and decoding errors. Apply the policy at the actual repository file-reading boundaries, not by global string replacement or modifying os.environ.

See development-tests.py in this directory for public examples. Deliver original-failing regression tests at the authorized test path without changing existing test controls or dependencies. Document behavior, boundaries, and compatibility policy at the authorized documentation path. Private verification runs independently; public examples do not cover every boundary.
