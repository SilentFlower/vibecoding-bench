# Engineering contract: CONFIGARGPARSE-O04-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add ArgumentParser.discover_config_files() for declared default_config_files only. Return ordered fresh records matching existing glob expansion and duplicate source order: path records contain kind,index,path,exists; unmatched declarations produce exists=false; provider records contain only kind="provider",index,executed=false. Support PathLike and expanduser with path-before-callable precedence. Do not open files, invoke providers, inspect their repr, run argument actions or mutate last parse/source state. Discovery is a filesystem snapshot, not a promise of later readability; real parsing behavior stays unchanged.

Deliver meaningful original-failing public regression tests at library/tests/test_development_configargparse_o04_dev.py and concise English compatibility documentation at library/docs/development-configargparse-o04-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/configargparse.py
- library/tests/test_development_configargparse_o04_dev.py
- library/docs/development-configargparse-o04-dev.md
