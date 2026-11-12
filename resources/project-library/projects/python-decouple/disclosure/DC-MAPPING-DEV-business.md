# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add MappingCast(key_cast=str, value_cast=undefined, *, format='pairs', delimiter=',', duplicate='error'). Parse strict one-record CSV key=value pairs by splitting only the first equals sign, or explicitly selected JSON objects with native nested values. Convert each key/value once, detect duplicate keys after key conversion and support explicit duplicate='last'. Preserve empty values and # characters; reject empty keys, missing separators, multiple records and non-object JSON without leaking entire values. None yields an empty mapping. Do not change Csv or guess formats automatically.

Deliver meaningful original-failing public regression tests at library/tests/test_development_dc_mapping_dev.py and concise English compatibility documentation at library/docs/development-dc-mapping-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/decouple.py
- library/tests/test_development_dc_mapping_dev.py
- library/docs/development-dc-mapping-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
