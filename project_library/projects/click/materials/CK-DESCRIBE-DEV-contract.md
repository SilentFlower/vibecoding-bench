# Engineering contract: CK-DESCRIBE-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Command.describe(ctx) returning an independent info dictionary with all existing to_info_dict fields plus usage=self.get_usage(ctx) and command_path=ctx.command_path. Require ctx.command is self. Respect actual parent/group invocation names, custom usage/formatter settings and subclass metadata overrides, without invoking command callbacks, parsing values or changing the original to_info_dict schema. Work for groups, aliases and nested commands; metadata remains Python data with existing value types rather than claiming arbitrary values are JSON serializable.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ck_describe_dev.py and concise English compatibility documentation at library/docs/development-ck-describe-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/click/core.py
- library/development_tests/test_development_ck_describe_dev.py
- library/docs/development-ck-describe-dev.md
