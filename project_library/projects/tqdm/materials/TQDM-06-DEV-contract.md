# Engineering contract: TQDM-06-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair built-in utils.envwrap boolean inference for actual bool/Optional[bool] annotations, bool defaults and explicit types fallback. Parse case-insensitive stripped true/false/1/0/yes/no/on/off, reject unknown/empty text clearly with parameter name and preserve direct-call argument precedence. Do not turn string-typed "False" into bool, change int/float/union inference or evaluate symbolic annotations as code. Keep environment-name prefixes/app precedence and external optional envwrap provider delegation untouched; this delivery targets the pinned built-in provider. Validate with isolated patched synthetic env keys only, no real credential/config changes.

Deliver real implementation, original-failing public tests at library/tests/test_development_tqdm_06_dev.py, and English compatibility documentation at library/docs/development-tqdm-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/tqdm/utils.py
- library/tests/test_development_tqdm_06_dev.py
- library/docs/development-tqdm-06-dev.md
