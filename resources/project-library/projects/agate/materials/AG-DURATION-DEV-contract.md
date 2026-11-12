# Engineering contract: AG-DURATION-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Extend Median and Percentiles to TimeDelta columns while preserving the existing CDF rank rule and Number behavior. Return timedelta values and report a TimeDelta aggregate type for Median. Ignore nulls using the existing warning policy, return None values for empty data, and compute duration midpoints without overflow at timedelta extremes or floating-point loss. Fractional microseconds round to nearest even. Preserve original source tests and Quantiles behavior.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ag_duration_dev.py and concise English compatibility documentation at library/docs/development-ag-duration-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/agate/aggregations/median.py
- library/agate/aggregations/percentiles.py
- library/development_tests/test_development_ag_duration_dev.py
- library/docs/development-ag-duration-dev.md
