# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Register typed_list(item_check="string", force=True, min=None, max=None) in Validator using the same instance registered checks. Accept list/tuple or, only when force is true, one scalar; never split a string into characters. Normalize force from schema true/false, enforce lengths, convert every element with Validator.check, return a fresh list and keep input unchanged. Add VdtListItemError with zero-based index and original cause, excluding the original value from its message. Preserve custom check behavior and all existing force_list/int_list/None checks; a real ConfigObj configspec must use this validator.

Deliver meaningful original-failing public regression tests at library/tests/test_development_configobj_o04_dev.py and concise English compatibility documentation at library/docs/development-configobj-o04-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/configobj/validate.py
- library/tests/test_development_configobj_o04_dev.py
- library/docs/development-configobj-o04-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
