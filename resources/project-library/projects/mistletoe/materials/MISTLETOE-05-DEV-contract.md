# Engineering contract: MISTLETOE-05-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add explicit filename "-" support to the existing CLI: read stdin as exactly one complete Markdown document, emit UTF-8 renderer output without interactive banner/prompts, and exit normally at EOF including empty input. Allow one stdin entry among ordinary files in argument order; reject repeated "-" before conversion. Preserve no-filename interactive mode, file opening errors, custom renderers and normal file output.

Deliver real implementation, original-failing public tests at library/tests/test_development_mistletoe_05_dev.py, and English compatibility documentation at library/docs/development-mistletoe-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/mistletoe/cli.py
- library/tests/test_development_mistletoe_05_dev.py
- library/docs/development-mistletoe-05-dev.md
