# Engineering contract: AG-WEIGHTED-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add exported WeightedMean(value_column, weight_column) and WeightedVariance(value_column, weight_column) aggregations. Both columns must use Number. Operate on same-row pairs, skip a pair if either member is null, reject negative or nonfinite weights and nonfinite values, preserve Decimal arithmetic, and return None for no positive total weight. WeightedVariance is population variance, sum(w*(x-mean)**2)/sum(w), not a sample estimator. Support TableSet aggregation and preserve all existing aggregations.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ag_weighted_dev.py and concise English compatibility documentation at library/docs/development-ag-weighted-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/agate/aggregations/weighted.py
- library/agate/aggregations/__init__.py
- library/development_tests/test_development_ag_weighted_dev.py
- library/docs/development-ag-weighted-dev.md
