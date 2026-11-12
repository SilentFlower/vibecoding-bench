# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add ConfigObj.write_atomic(filename=None), preserving ordinary write/outfile behavior. Serialize a raw-preserving clone through the real ConfigObj writer before opening any temporary file; use a unique same-directory temporary, preserve existing permission bits or use 0600 for a new file, close before os.replace and clean only the operation temp on failure. Default to self.filename, support PathLike, reject missing destination and symlink targets, return the absolute destination. Serialization/encoding/replace errors must preserve old bytes and original in-memory metadata. Do not promise power-loss durability or cross-file atomicity.

Deliver meaningful original-failing public regression tests at library/tests/test_development_configobj_o03_dev.py and concise English compatibility documentation at library/docs/development-configobj-o03-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/configobj/__init__.py
- library/tests/test_development_configobj_o03_dev.py
- library/docs/development-configobj-o03-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
