# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add packaging.utils.build_wheel_filename(name,version,tags,build=()) and build_sdist_filename(name,version,extension=".tar.gz"). Validate/normalize project names and versions using existing APIs. Stable compressed tag components must parse back to the EXACT supplied Tag set; reject non-Cartesian sets instead of inventing compatibility. Validate build tuple and exact roundtrip, reject empty tags and invalid suffix/components. Sdist supports tar.gz/zip, canonical underscore escape. Never create/install archives or alter parsing permissiveness.

Deliver real implementation, original-failing public tests at library/tests/test_development_packaging_05_dev.py, and English compatibility documentation at library/docs/development-packaging-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/packaging/utils.py
- library/tests/test_development_packaging_05_dev.py
- library/docs/development-packaging-05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
