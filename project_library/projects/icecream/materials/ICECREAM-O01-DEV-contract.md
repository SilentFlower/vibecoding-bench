# Engineering contract: ICECREAM-O01-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix actual IceCreamDebugger._formatArgs so ast.Starred expansion never truncates calculated values via zip. Preserve reliably identifiable ordinary prefix/suffix expressions; label indeterminate expanded middle values explicitly by index without guessing source lengths or reevaluating/reiterating expressions/generators. Support multiple/empty expansions, ordinary args between stars, no-source fallback and single/multiple passthrough object identity. Keep ordinary nonstar source/literal formatting unchanged and ensure every calculated argument appears once in output.

Deliver meaningful original-failing public regression tests at library/tests/test_development_icecream_o01_dev.py and concise English compatibility documentation at library/docs/development-icecream-o01-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/icecream/icecream.py
- library/tests/test_development_icecream_o01_dev.py
- library/docs/development-icecream-o01-dev.md
