# Safe interval sampling

Pinned source: https://github.com/AlexandreDecan/portion @ 622e7ca1f3a36a7cb337e6f51abeef0ee5e40c44.

Extend the actual portion.iterate API with keyword-only checked=False and max_items=None. With checked=True, each evaluated numeric or callable step must strictly advance in the requested direction; reject a zero/stagnating/wrong-direction step with ValueError, including while skipping an open starting boundary. max_items is a nonnegative integer excluding bool, limits total yielded values across disjoint atomic parts, and 0 must return without invoking base or step. Stop at the limit without an extra step call. Keep default legacy behavior, lazy finite prefixes of unbounded intervals, custom date steps and bases, reverse ordering, existing callback exceptions, all original tests and specialized create_api exports. Do not use wall clocks, background threads or eager enumeration to simulate a limit.

See development-tests.py for the public reproduction. Deliver meaningful original-failing regressions at library/tests/test_development_checked_iterate.py and add compatibility documentation. The pinned source distribution version is 2.7.0-pre1; independent verification supplies version metadata through its existing trusted native binding rather than installing a second implementation.
