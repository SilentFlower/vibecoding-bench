# Engineering contract: CF-TOML-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement confuse.toml_source.TomlSource(filename,default=False,base_for_paths=False,optional=False) as a ConfigSource. Read standard TOML including tables, arrays and dates; keep absolute filename and metadata. load() parses fully before replacing the same source dictionary, removes deleted keys, preserves last valid state on parse/read error and raises ConfigReadError. Optional missing files become empty, other failures remain errors. Configuration.reload must reload TOML and existing YAML without replacing source identities or disturbing in-memory sources. Do not alter YAML parsing.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_cf_toml_dev.py and concise English compatibility documentation at library/docs/development-cf-toml-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/confuse/toml_source.py
- library/confuse/core.py
- library/development_tests/test_development_cf_toml_dev.py
- library/docs/development-cf-toml-dev.md
