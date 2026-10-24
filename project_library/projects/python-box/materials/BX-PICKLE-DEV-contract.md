# Engineering contract: BX-PICKLE-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Repair trusted-local pickle roundtrips for Box subclasses: root, direct/deep mapping children and mappings inside BoxList must preserve their actual classes and configuration for protocols 2 through the highest supported protocol. Preserve values, existing shared references, custom instance state, default_box/conversion_box/frozen_box options and frozen mutation guards. Restore configuration before replaying items, do not rerun business __init__, globally register pickle hooks or change normal construction and YAML/JSON conversion. Ordinary Box and BoxList must retain frozen upstream behavior.

Deliver meaningful original-failing public regression tests at library/test/test_development_bx_pickle_dev.py and concise English compatibility documentation at library/docs/development-bx-pickle-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/box/box.py
- library/box/box_list.py
- library/test/test_development_bx_pickle_dev.py
- library/docs/development-bx-pickle-dev.md
