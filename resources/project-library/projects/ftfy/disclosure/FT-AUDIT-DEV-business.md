# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement ftfy.audit.repair(text,config=None) returning frozen RepairResult(source_sha256,input_length,text,changed,explanation). Call actual fix_and_explain, retain explanation=None when disabled without changing any fixer policy (requires completed explanation-config repair); otherwise freeze steps and verify actual apply_plan replays to the returned result. Hash original Unicode using UTF8 surrogatepass, do not retain original plaintext in result, preserve input/config, distinguish unchanged text from an absent explanation, and do not fabricate generic repair reasons.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ft_audit_dev.py and concise English compatibility documentation at library/docs/development-ft-audit-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/ftfy/audit.py
- library/development_tests/test_development_ft_audit_dev.py
- library/docs/development-ft-audit-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
