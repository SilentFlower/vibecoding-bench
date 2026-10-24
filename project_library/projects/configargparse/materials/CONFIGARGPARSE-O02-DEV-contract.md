# Engineering contract: CONFIGARGPARSE-O02-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add JSONConfigFileParser as a ConfigFileParser accepting object roots, finite JSON scalars and flat scalar lists. Normalize bool to true/false and other scalar values to strings for the existing actual ArgumentParser action pipeline. Reject null, nested objects/lists, non-object roots, invalid JSON/encoding and NaN/Infinity. duplicates defaults to error and supports last/warn explicitly; never include values in duplicate diagnostics. Serialize supported values to Unicode-preserving valid JSON with roundtrip behavior; optional YAML must not be imported.

Deliver meaningful original-failing public regression tests at library/tests/test_development_configargparse_o02_dev.py and concise English compatibility documentation at library/docs/development-configargparse-o02-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/configargparse.py
- library/tests/test_development_configargparse_o02_dev.py
- library/docs/development-configargparse-o02-dev.md
