# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add python -m liquid.project_cli and callable main(argv) using real Environment/FileSystemLoader/StrictUndefined, explicit --root --template --data --output. Require object JSON, local root-contained nonabsolute/non-parent-traversing template and root-contained resolved source; output cannot replace input JSON or any template-root file. Render completely before creating same-output-directory temp file, flush/fsync and os.replace atomically; cleanup on failure preserves existing output and prints only safe error type with exit2. Unicode, include/render, empty output and actual saved file must work. No network or credential lookup, no environment-data guessing, no source/config/test changes.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_liquid_06_dev.py, and English compatibility documentation at library/docs/development-python-liquid-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/liquid/project_cli.py
- library/tests/test_development_python_liquid_06_dev.py
- library/docs/development-python-liquid-06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
