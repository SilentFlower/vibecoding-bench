# Engineering contract: PYPIKA-01-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair the standalone MICROSECOND interval branch to apply the sign already recorded by Interval.__init__. Negative arbitrarily large integer microseconds must serialize consistently across supported dialect templates, repeatably without mutation. Keep positive, zero, mixed-unit, week and quarter policies unchanged; do not invent mixed-sign normalization. SQL dialect claims concern text generation only.

Deliver real implementation, original-failing public tests at library/tests/test_development_pypika_01_dev.py, and English compatibility documentation at library/docs/development-pypika-01-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/pypika/terms.py
- library/tests/test_development_pypika_01_dev.py
- library/docs/development-pypika-01-dev.md
