# Engineering contract: JSONSCHEMA-O01-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix draft-2019-09 find_evaluated_item_indexes_by_schema so boolean single-schema items is never treated as a tuple and len(bool) never occurs under unevaluatedItems. items=true evaluates all array positions; items=false must still yield standard validation failure for nonempty arrays and accept empty arrays without TypeError. Preserve tuple/additionalItems behavior, successful combinator annotations, nonarray handling and independent draft-2020-12 prefixItems semantics. Use actual Draft201909Validator paths, not special-case input data or disable unevaluatedItems.

Deliver meaningful original-failing public regression tests at library/tests/test_development_jsonschema_o01_dev.py and concise English compatibility documentation at library/docs/development-jsonschema-o01-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/jsonschema/_legacy_keywords.py
- library/tests/test_development_jsonschema_o01_dev.py
- library/docs/development-jsonschema-o01-dev.md
