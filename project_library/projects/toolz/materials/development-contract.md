# Fix collisions between a partition padding sentinel and real business text

Pinned source: https://github.com/pytoolz/toolz @ 451af60dec590a6010e2babdbf391ea8f815122f.

Repair partition and partition_all so any ordinary string, specifically the pinned implementation's '__no__pad__' literal, remains real data and can also be an explicitly supplied padding value. Missing slots must be recognized by an unambiguous internal identity marker, never by comparing business values. Preserve tuple batches, default truncation for partition, partial final groups for partition_all, lazy finite prefixes of infinite input, existing at-most-one-batch lookahead, original invalid-__len__ diagnostics, top-level/curried APIs, and all existing frozen tests.

See development-tests.py in this directory for public examples. Deliver original-failing regression tests at the authorized test path without changing existing test controls or dependencies. Document behavior, boundaries, and compatibility policy at the authorized documentation path. Private verification runs independently; public examples do not cover every boundary.
