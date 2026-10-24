# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement inflect.templates.ReportTemplate(text) with compiled unique fields and render(engine,values). Allow simple named placeholders and escaped braces; reject attribute/index access, conversion flags, arbitrary format specs and nested expressions at construction. Support raw text, :words, :ordinal, :article, :join and :counted(noun), using real engine APIs and completed counted/stream join implementations. Validate all required names before formatting, preserve repeated fields/literal braces and custom noun rules. Work on an isolated clone so number formatting does not mutate original state. No eval or method dispatch from template text; content values are not reparsed as templates.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_if_template_dev.py and concise English compatibility documentation at library/docs/development-if-template-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/inflect/templates.py
- library/development_tests/test_development_if_template_dev.py
- library/docs/development-if-template-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
