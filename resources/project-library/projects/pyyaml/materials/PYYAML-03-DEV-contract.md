# Engineering contract: PYYAML-03-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add yaml.strict.StrictSafeLoader/strict_load as opt-in safe parsing. Detect duplicate EXPLICIT keys in each MappingNode before flattening, using constructed key equality including 1/true, raise ConstructorError with first and repeated marks. Inherited merge keys and one local override are not explicit duplicates; preserve alias reuse and default yaml.safe_load last-wins behavior. No global resolver/constructor registrations, no arbitrary Python objects or blanket merge rejection.

Deliver real implementation, original-failing public tests at library/tests/test_development_pyyaml_03_dev.py, and English compatibility documentation at library/docs/development-pyyaml-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/lib/yaml/strict.py
- library/tests/test_development_pyyaml_03_dev.py
- library/docs/development-pyyaml-03-dev.md
