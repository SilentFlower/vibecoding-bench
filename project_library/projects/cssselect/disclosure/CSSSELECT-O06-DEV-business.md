# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add cssselect.editable.EditableStateTranslator supporting :read-write/:read-only as exact complements in the selected tree scope. Text-like input/textarea require no readonly/disabled and use the inherited static fieldset-disabled policy; exclude hidden/range/color/button/submit/reset/image/checkbox/radio/file inputs. Form controls never become editable merely from contenteditable ancestors. Other elements inherit the nearest valid contenteditable empty/true/plaintext-only/false declaration case-insensitively; invalid values inherit, false blocks. Support XHTML namespaced declarations, default read-only, preserve GenericTranslator rejection and document snapshot limitations (no scripts/designMode or improved fieldset approximation).

Deliver meaningful original-failing public regression tests at library/tests/test_development_cssselect_o06_dev.py and concise English compatibility documentation at library/docs/development-cssselect-o06-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/cssselect/editable.py
- library/tests/test_development_cssselect_o06_dev.py
- library/docs/development-cssselect-o06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
