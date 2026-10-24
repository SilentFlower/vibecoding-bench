# Engineering contract: CONFIGARGPARSE-O05-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement DispatchConfigFileParser(parsers, *, fallback=None, output_format=None) with an application-owned extension registry of ConfigFileParser instances/classes. Normalize suffix case, reject duplicate normalized extensions and invalid parser registrations. Dispatch once from stream.name without reading/rewinding/sniffing/importing; unknown or unnamed sources require explicit fallback. Propagate actual parse and optional dependency errors. Serialization requires an explicitly registered output_format and delegates to that parser. Preserve existing CompositeConfigParser and support nonseek streams.

Deliver meaningful original-failing public regression tests at library/tests/test_development_configargparse_o05_dev.py and concise English compatibility documentation at library/docs/development-configargparse-o05-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/configargparse.py
- library/tests/test_development_configargparse_o05_dev.py
- library/docs/development-configargparse-o05-dev.md
