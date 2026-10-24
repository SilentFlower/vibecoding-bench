# Engineering contract: DE-VALIDATION-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement dotenv.validation.parse_config(text, *, required=(), duplicates="error") returning immutable ParsedConfig(values, lines), using the pinned parser and its actual original line numbers. Collect syntax, duplicate and missing/value-less required-key issues into ConfigValidationError.issues tuples (code,key,line), in source order then required order; errors must not include secret values. Empty assigned values satisfy required. duplicates="last" preserves last definition and its line. Do not interpolate, touch os.environ, print secret content, or change permissive dotenv_values behavior.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_de_validation_dev.py and concise English compatibility documentation at library/docs/development-de-validation-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/dotenv/validation.py
- library/development_tests/test_development_de_validation_dev.py
- library/docs/development-de-validation-dev.md
