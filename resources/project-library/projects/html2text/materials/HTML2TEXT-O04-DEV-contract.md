# Engineering contract: HTML2TEXT-O04-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add image_density=None opt-in selection to actual img conversion, not a standalone unused parser. For finite positive nonbool numeric targets, parse unordered x-density srcset candidates (unmarked means 1x), select the smallest density >= target or largest available, and resolve through existing baseurl/link behavior. Permit missing src when srcset is sufficient. Explicitly reject duplicate/nonpositive/nonfinite/malformed/mixed w descriptors; document data: sets containing ambiguous commas as unsupported and retain src. Default None uses src unchanged, images_to_alt/ignore_images bypass unused source parsing, and HTML-image output uses the chosen source. Do not fetch resources or infer CSS layout.

Deliver meaningful original-failing public regression tests at library/test/test_development_html2text_o04_dev.py and concise English compatibility documentation at library/docs/development-html2text-o04-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/html2text/__init__.py
- library/test/test_development_html2text_o04_dev.py
- library/docs/development-html2text-o04-dev.md
