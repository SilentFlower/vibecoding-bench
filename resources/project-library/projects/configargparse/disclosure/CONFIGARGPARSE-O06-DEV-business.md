# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Build MappedJSONConfigFileParser(paths, *, unknown="error", duplicates="error") on the accepted JSON parser. paths maps explicit nonempty string tuples to unique flat action keys. Distinguish a literal dotted key from nested paths; reject prefix conflicts, duplicate destination keys, scalar/table conflicts, unsupported values and unknown leaves by default. Missing paths stay absent; unknown="ignore" is explicit. Scalars/lists must use the existing JSON conversion and actual ArgumentParser type/action pipeline. Serialize flat mapped settings back to the matching nested JSON object without changing inputs or allowing unknown output keys; preserve duplicate and finite-number controls.

Deliver meaningful original-failing public regression tests at library/tests/test_development_configargparse_o06_dev.py and concise English compatibility documentation at library/docs/development-configargparse-o06-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/configargparse.py
- library/tests/test_development_configargparse_o06_dev.py
- library/docs/development-configargparse-o06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
