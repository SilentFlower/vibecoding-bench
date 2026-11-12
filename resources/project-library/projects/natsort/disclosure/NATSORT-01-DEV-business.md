# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair the actual Natsort CLI numeric filtering: default int/i mode must preserve arbitrary-size integer tokens and exact decimal thresholds through argument parsing, inclusive range/reverse-range and exclusion comparisons. Do not round thresholds or tokens to float; fractional boundaries compare without truncation. Float/f/real/r retain existing float semantics. Invalid or nonfinite integer thresholds fail clearly. Preserve sorting, sign/exponent policy, Unicode token recognition and ordinary CLI behavior.

Deliver real implementation, original-failing public tests at library/tests/test_development_natsort_01_dev.py, and English compatibility documentation at library/docs/development-natsort-01-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/natsort/__main__.py
- library/tests/test_development_natsort_01_dev.py
- library/docs/development-natsort-01-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
