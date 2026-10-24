# Engineering contract: CONFIGOBJ-O02-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Extend Section.merge(indict, *, comments="incoming") so Section inputs retain raw interpolations, key/section comments and inline comments while cloning incoming data and rebinding newly inserted sections to the target main/parent/depth. Default incoming metadata wins; comments="existing" retains metadata of preexisting names; repeated merges do not accumulate duplicate comments. Plain dict inputs have no comment metadata and preserve existing comments. Keep recursive value overwrite behavior, reject invalid policies and never mutate or attach source Section objects.

Deliver meaningful original-failing public regression tests at library/tests/test_development_configobj_o02_dev.py and concise English compatibility documentation at library/docs/development-configobj-o02-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/configobj/__init__.py
- library/tests/test_development_configobj_o02_dev.py
- library/docs/development-configobj-o02-dev.md
