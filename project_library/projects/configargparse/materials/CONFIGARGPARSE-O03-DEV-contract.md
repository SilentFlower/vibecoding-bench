# Engineering contract: CONFIGARGPARSE-O03-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement ArgumentParser.parse_result with the existing parse_known_args inputs and a public ParseResult. Return actual parsed Namespace, ordered unknown tuple and source records identifying dest/value without retaining argparse.Action objects. Snapshot deeply at completion and return independent namespace/source accessor copies, including mutable defaults, append lists and custom Namespace attributes. Reusing the parser, changing defaults, mutating caller namespace/accessor values or a later failed parse must not change the earlier result. Keep parse_args and get_source_to_settings_dict behavior unchanged.

Deliver meaningful original-failing public regression tests at library/tests/test_development_configargparse_o03_dev.py and concise English compatibility documentation at library/docs/development-configargparse-o03-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/configargparse.py
- library/tests/test_development_configargparse_o03_dev.py
- library/docs/development-configargparse-o03-dev.md
