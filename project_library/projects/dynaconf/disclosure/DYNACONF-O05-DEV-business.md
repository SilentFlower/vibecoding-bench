# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Settings.set_value_parser(parser=None,*,errors="raise") selecting JSON, ast.literal_eval, a local callable or default TOML for this instance only, integrated at actual _parse_conf_data for tomlfy=True unmarked strings including env_loader. Existing explicit @str/@int/@json/@merge/lazy tokens keep priority; nonstrings/non-tomlfy values stay unchanged. Validate profile/error policies before writing config. Raise or retain original string only for declared parse ValueError/SyntaxError; propagate programming failures. Show actual JSON null/array differences versus an independent default instance and allow resetting None without modifying global converters.

Deliver meaningful original-failing public regression tests at library/tests/test_development_dynaconf_o05_dev.py and concise English compatibility documentation at library/docs/development-dynaconf-o05-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/dynaconf/base.py
- library/dynaconf/utils/parse_conf.py
- library/tests/test_development_dynaconf_o05_dev.py
- library/docs/development-dynaconf-o05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
