# Engineering contract: CONFIGOBJ-O06-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add ConfigObj.validated_reload(validator) using the actual original filename/options/configspec and the accepted fixed validation report. Build an independent candidate from disk, force missing-file failure without creating a file, revalidate actual types/defaults, return valid=false without touching the old tree on validation errors and propagate IO/parse/callback exceptions. Only successful validation replaces all values and metadata, retaining the caller root identity and reconnecting parent/main/depth plus cached interpolation engines. Keep original options and ordinary reload behavior; never cache implicit validator state.

Deliver meaningful original-failing public regression tests at library/tests/test_development_configobj_o06_dev.py and concise English compatibility documentation at library/docs/development-configobj-o06-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/configobj/__init__.py
- library/tests/test_development_configobj_o06_dev.py
- library/docs/development-configobj-o06-dev.md
