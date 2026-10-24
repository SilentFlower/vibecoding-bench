# Engineering contract: FLASK-O04-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Extend Config.from_prefixed_env with opt-in atomic=False and strict=False. Atomic mode stages a deep detached dictionary, parses sorted matching variables and validates nonempty nested path segments plus dictionary intermediates before any self mutation; errors name the full environment key and preserve all prior nested external aliases. Non-strict atomic mode retains text on declared parse ValueError/TypeError; strict atomic raises, and custom loader programming errors propagate. Valid batches commit together. Keep default legacy loading behavior exactly, require strict with atomic explicitly, and do not silently swallow conflicts or call a failed partial batch successful.

Deliver meaningful original-failing public regression tests at library/tests/test_development_flask_o04_dev.py and concise English compatibility documentation at library/docs/development-flask-o04-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/flask/config.py
- library/tests/test_development_flask_o04_dev.py
- library/docs/development-flask-o04-dev.md
