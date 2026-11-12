# Engineering contract: JINJA-O03-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix binary Python generation for Pow so the entire Jinja AST left operand is grouped even when a negative Const is generated. Dynamic and constant/optimized/nonoptimized negative-base powers must agree for multiple bases and odd/even/zero/negative exponents. Preserve documented Jinja left-associative power chains (2**3**2=64), actual variable operands and sandbox intercepted-binop callback semantics. Do not merely special-case -1, change parser associativity or broadly alter unrelated generated binary expressions.

Deliver meaningful original-failing public regression tests at library/tests/test_development_jinja_o03_dev.py and concise English compatibility documentation at library/docs/development-jinja-o03-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/jinja2/compiler.py
- library/tests/test_development_jinja_o03_dev.py
- library/docs/development-jinja-o03-dev.md
