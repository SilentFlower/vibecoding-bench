# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add respect_xml_space=False parse handler option. When enabled, xml:space="preserve" disables stripping for that element, inherited descendants and comments; xml:space="default" restores the caller original strip_whitespace policy in that subtree. Restore parent policy when an element closes, including item_depth callback paths, so siblings do not leak state. Recognize raw xml:space and expanded XML namespace attributes with configured separator; unknown values inherit. Preserve exposed attribute values, legacy default behavior and concatenation semantics, without promising ordered mixed-content fidelity.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_xd_xml_space_dev.py and concise English compatibility documentation at library/docs/development-xd-xml-space-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/xmltodict.py
- library/development_tests/test_development_xd_xml_space_dev.py
- library/docs/development-xd-xml-space-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
