# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Extend FileUpload.save, static_file, BaseTemplate name/lookup and ResourceManager.add_path boundaries to accept str/bytes/os.PathLike via os.fspath/fsdecode, including custom PathLike and Unicode. Distinguish real paths from writable streams, support upload target directories and one directory lookup input, preserve caller stream ownership/cursor and existing file conflict/static containment rules. Invalid __fspath__ return types must fail instead of being stringified. Do not reinterpret template source text as filenames.

Deliver meaningful original-failing public regression tests at library/test/test_development_bottle_o01_dev.py and concise English compatibility documentation at library/docs/development-bottle-o01-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/bottle.py
- library/test/test_development_bottle_o01_dev.py
- library/docs/development-bottle-o01-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
