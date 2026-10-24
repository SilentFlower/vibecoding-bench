# Business scope

Preserve the original text and newline bytes of every non-target parsed record when set_key or unset_key edits a UTF-8 file. Keep existing LF serialization of changed or newly appended target lines and existing return values, quoting, file modes, symlink behavior and failure cleanup. Add focused public tests. The attached reproduction and contract are complete; no earlier answer is required.

# Investigation topics

- Locate changes to unrelated newlines by inspecting the actual bytes.

# Supplied business material: materials/newline-reproduction.md

# Synthetic byte-preservation reproduction
Create a dedicated temporary UTF-8 file with before_hex below. Call set_key(path, "COLOR", "new"). The original version reports (True, "COLOR", "new") and changes unrelated CRLF comments and the multi-line KEEP record to LF. The target line remains LF by existing design. Compare exact bytes and separately read KEEP with dotenv_values.

Before escaped: b'# untouched\r\nKEEP="first\r\nsecond"\r\nCOLOR=old\r\n'
Before hex: 2320756e746f75636865640d0a4b4545503d2266697273740d0a7365636f6e64220d0a434f4c4f523d6f6c640d0a
After original escaped: b'# untouched\nKEEP="first\nsecond"\nCOLOR=\'new\'\n'
After original hex: 2320756e746f75636865640a4b4545503d2266697273740a7365636f6e64220a434f4c4f523d276e6577270a


# Supplied business material: materials/newline-contract.md

# Edit contract
Preserve the original text/newline bytes of every non-target parsed record for set_key and unset_key in UTF-8 files: CRLF, LF, CR, mixed comments/blank lines/multi-line values. Changed or appended target lines keep LF. Preserve return tuples, quoting/escaping, duplicate-target replacement, modes, symlink behavior, errors and temporary-file cleanup. Retain the existing append separator rule: a final record not ending in LF causes one LF separator before an appended key, including the existing CR-only case. This does not add BOM preservation, dominant-newline detection, or change read-only APIs. Add meaningful focused tests in library/tests/test_main.py.

