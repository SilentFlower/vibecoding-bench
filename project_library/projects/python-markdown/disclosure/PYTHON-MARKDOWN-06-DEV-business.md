# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add markdown.documents.convert_file(input,output=None,input_encoding="utf-8",output_encoding="utf-8",close_input=False,**options), building on the earlier real ConversionResult API. Accept string/PathLike paths, standard text/binary input streams from the current cursor and standard text/binary output streams; decode/encode once with independent explicit encodings. Keep caller streams open unless close_input is explicitly true, never close output or retry a failed write with another type. Owned path IO closes itself; return the actual structured result. Prepare encoding before touching output paths, use same-directory temporary flush/fsync+replace, preserve existing mode, reject symlink/nonregular output and clean temporary files. Read/convert/encoding/replace failures remain explicit and keep old output bytes before replacement. Existing file APIs are unchanged.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_markdown_06_dev.py, and English compatibility documentation at library/docs/development-python-markdown-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/markdown/documents.py
- library/tests/test_development_python_markdown_06_dev.py
- library/docs/development-python-markdown-06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
