# Engineering contract: CSSSELECT-O04-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement cssselect.extensions.PluginTranslator and HTMLPluginTranslator using an instance-local registry without replacing existing subclass mechanisms. register_pseudo(name, callback, *, functional=False,min_args=0,max_args=None,version="1") validates literal names, arity, callable/version, refuses duplicates or builtin static/function names, and returns self. Static callbacks receive actual XPathExpr; functions additionally receive the real Function/Token node. Validate invocation form, arity and XPathExpr return type. Preserve normal XML/HTML/XHTML behavior and native callbacks/errors; expose deterministic extension_fingerprint capability/version declarations and ensure registry isolation.

Deliver meaningful original-failing public regression tests at library/tests/test_development_cssselect_o04_dev.py and concise English compatibility documentation at library/docs/development-cssselect-o04-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/cssselect/extensions.py
- library/tests/test_development_cssselect_o04_dev.py
- library/docs/development-cssselect-o04-dev.md
