# Complete callback traces

Same retry predicate: FileNotFoundError. Total attempt bound: 3. Fixed wait: 0.2; the sleep spy records arguments without waiting. First success has before=1, after=0, before_sleep=0, sleep=0. Two missing-file failures then success have before=3, after=2, before_sleep=2, sleep=2. Permanent missing-file failure has before=3, after=3, before_sleep=2, sleep=2. A non-retryable JSONDecodeError has before=1, after=0. Trace the real controller action order, not only these counts.
